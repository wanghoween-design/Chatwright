"""浏览器生命周期管理：用 Playwright 驱动 Chromium，并支持登录态持久化。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

# 登录态（cookie / localStorage）持久化目录，避免每次都手动登录
STATE_DIR = Path(__file__).resolve().parent.parent.parent / "state"
# 默认登录态文件（DeepSeek 沿用此名，向后兼容）
DEFAULT_STATE_FILENAME = "deepseek_storage.json"


class BrowserManager:
    """管理一个常驻的 Chromium 浏览器与页面实例。

    v0 使用单页面单会话：MCP Server 启动即开浏览器，所有 tool 调用复用同一页面，
    从而保留登录态与对话上下文。

    支持多平台独立登录态：通过 state_filename 给每个平台一个独立的 JSON 文件，
    避免 Kimi / Qwen / DeepSeek 互相覆盖 cookie。
    """

    def __init__(
        self,
        headless: bool = True,
        state_filename: str = DEFAULT_STATE_FILENAME,
        load_storage: bool = True,
        persistent: bool = False,
    ):
        self.headless = headless
        self.state_path: Path = STATE_DIR / state_filename
        self.load_storage = load_storage  # False = 不加载旧登录态（用于重新登录）
        # persistent=True：用真实浏览器配置目录持久化全部状态
        # （cookie / sessionStorage / IndexedDB 等），解决部分网站登录态
        # 只存在 sessionStorage 或浏览器指纹里、普通 storage_state 存不住的问题
        self.persistent = persistent
        self.profile_dir: Path | None = None
        if persistent and state_filename:
            self.profile_dir = STATE_DIR / (Path(state_filename).stem + "_profile")
        self._pw = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def start(self) -> Page:
        self._pw = await async_playwright().start()
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        if self.persistent and self.profile_dir:
            # 持久化模式：整个浏览器配置目录都在本地，登录状态天然保留
            self.browser = None
            first_run = not self.profile_dir.exists()
            self.context = await self._pw.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=self.headless,
                viewport={"width": 1280, "height": 900},
            )
            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
            # 首次使用 profile 时，把旧的 storage_state JSON 导入，免去重新登录
            if first_run:
                await self._migrate_old_state()
            return self.page

        self.browser = await self._pw.chromium.launch(headless=self.headless)
        if self.state_path.exists() and self.load_storage:
            # 复用上次保存的登录态
            self.context = await self.browser.new_context(storage_state=str(self.state_path))
        else:
            self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
        # 统一的中文视口，避免移动端布局导致选择器失效
        await self.page.set_viewport_size({"width": 1280, "height": 900})
        return self.page

    async def save_state(self) -> None:
        """把当前登录态落盘，下次启动自动复用。"""
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        if self.persistent:
            return  # 持久化 profile 自动保存，无需额外操作
        await self.context.storage_state(path=str(self.state_path))

    async def stop(self) -> None:
        if self.context:
            try:
                if self.persistent:
                    await self.context.close()  # 持久上下文关闭即保存全部状态
                elif self.browser:
                    await self.browser.close()
            except Exception:
                pass
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
        self.browser = None
        self.context = None
        self.page = None

    async def _migrate_old_state(self) -> None:
        """首次创建 profile 时，把旧的 storage_state JSON 导入，免去重新登录。"""
        if not self.state_path.exists() or self.profile_dir is None:
            return
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return
        try:
            for cookie in data.get("cookies") or []:
                try:
                    await self.context.add_cookies([cookie])
                except Exception:
                    pass
            for origin in data.get("origins") or []:
                origin_url = origin.get("origin")
                # storage_state 的 localStorage 是 [{name, value}] 数组格式
                for item in origin.get("localStorage") or []:
                    key, value = item.get("name"), item.get("value")
                    if not origin_url or key is None or value is None:
                        continue
                    script = (
                        f"if (location.origin === {json.dumps(origin_url)}) "
                        f"localStorage.setItem({json.dumps(key)}, {json.dumps(value)});"
                    )
                    try:
                        await self.context.add_init_script(script)
                    except Exception:
                        pass
        except Exception:
            pass  # 迁移失败不阻断聊天（最多需要重新登录一次）

    def clear_persistent_state(self) -> bool:
        """删除持久化 profile 与旧登录态文件（注销登录用，需先 stop()）。"""
        removed = False
        if self.profile_dir and self.profile_dir.exists():
            shutil.rmtree(self.profile_dir, ignore_errors=True)
            removed = True
        if self.state_path.exists():
            self.state_path.unlink()
            removed = True
        return removed
