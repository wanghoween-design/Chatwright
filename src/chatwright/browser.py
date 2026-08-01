"""浏览器生命周期管理：用 Playwright 驱动 Chromium，并支持登录态持久化。"""

from __future__ import annotations

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
    ):
        self.headless = headless
        self.state_path: Path = STATE_DIR / state_filename
        self.load_storage = load_storage  # False = 不加载旧登录态（用于重新登录）
        self._pw = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def start(self) -> Page:
        self._pw = await async_playwright().start()
        self.browser = await self._pw.chromium.launch(headless=self.headless)
        STATE_DIR.mkdir(parents=True, exist_ok=True)
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
        await self.context.storage_state(path=str(self.state_path))

    async def stop(self) -> None:
        if self.browser:
            await self.browser.close()
        if self._pw:
            await self._pw.stop()
        self.browser = None
        self.context = None
        self.page = None
