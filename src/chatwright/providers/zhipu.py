"""智谱清言 ChatGLM 网页版 Provider（chatglm.cn）。

2026-08 实测：
  - 游客模式即可对话（有次数/积分限制，登录可解锁更多功能）
  - 输入框：textarea
  - 回复气泡：.markdown-body（AI 回复内容）
"""

from __future__ import annotations

import time

from playwright.async_api import Locator, Page

from .base import WebChatProvider

DEFAULT_URL = "https://chatglm.cn/main/all"


class ZhipuProvider(WebChatProvider):
    # 智谱思考/联网搜索停顿较长，需要更长稳定期与最短等待，防止截断
    WAIT_STABLE: float = 6.0
    WAIT_MIN: float = 18.0

    def __init__(self, page: Page, base_url: str = DEFAULT_URL):
        super().__init__(page, base_url)

    async def _after_open(self) -> None:
        if "login" in self.page.url:
            print("[Chatwright] 智谱检测到登录页，请在浏览器中手动登录。")
        if await self._verification_blocked():
            # 风控墙常为间歇性：先等待自动清除，持续存在才提示
            if not await self._wait_verification_clear(30):
                await self._restore_window()
                raise RuntimeError(
                    "智谱「访问验证」持续未通过（风控拦截）：已恢复窗口到前台，"
                    "请尝试在窗口里完成验证；若仍失败，可能是当前网络被风控，请稍后再试。"
                )

    async def _type_and_submit(self, message: str) -> None:
        # 先检查验证墙，避免白等 15 秒
        if await self._verification_blocked():
            if not await self._wait_verification_clear(30):
                await self._restore_window()
                raise RuntimeError(
                    "智谱「访问验证」持续未通过（风控拦截）：已恢复窗口到前台，"
                    "请尝试在窗口里完成验证；若仍失败，可能是当前网络被风控，请稍后再试。"
                )
        # 页面可能混入隐藏的脚本 textarea（如 CF 风控代码），只选可见的
        box = self.page.locator("textarea:visible").first
        await box.wait_for(state="visible", timeout=15000)
        await box.click()
        await box.fill(message)
        await self.page.keyboard.press("Enter")

    async def _bubbles(self) -> Locator:
        # 实测：AI 回复在 .markdown-body 里（.answer-content-wrap 是外层容器）
        return self.page.locator(".markdown-body, [class*='answer-content-wrap']")

    async def _is_generating(self) -> bool:
        """智谱有「联网搜索 / 思考」过程，期间文字会停顿，检测到生成指示就继续等。"""
        for text in ("停止", "正在思考", "正在搜索", "搜索中"):
            loc = self.page.locator(f"text={text}")
            n = await loc.count()
            for i in range(n):
                try:
                    if await loc.nth(i).is_visible():
                        return True
                except Exception:
                    continue
        # 生成中的加载动画 / 思考指示（可见才算）
        for cls in ("[class*='loading']", "[class*='thinking']", "[class*='generating']"):
            loc = self.page.locator(cls)
            n = await loc.count()
            for i in range(n):
                try:
                    if await loc.nth(i).is_visible():
                        return True
                except Exception:
                    continue
        return False

    async def _verification_blocked(self) -> bool:
        """检测智谱的「访问验证」滑块墙（无滑块通过就没有聊天页面）。"""
        for text in ("访问验证", "请按住滑块", "拖动到最右边"):
            loc = self.page.locator(f"text={text}")
            n = await loc.count()
            for i in range(n):
                try:
                    if await loc.nth(i).is_visible():
                        return True
                except Exception:
                    continue
        return False

    async def _wait_verification_clear(self, seconds: float = 30.0) -> bool:
        """等待验证墙自动消失（风控墙常为间歇性），返回是否已清除。"""
        start = time.monotonic()
        while time.monotonic() - start < seconds:
            if not await self._verification_blocked():
                return True
            await self.page.wait_for_timeout(2000)
        return False

    async def _check_interrupt(self) -> None:
        """等待回复期间若出现滑块验证墙：短时容忍（可能自动消失），持续才提示。"""
        visible = await self._verification_blocked()
        if self._modal_persisted(visible, timeout=10.0):
            await self._restore_window()
            raise RuntimeError(
                "智谱「访问验证」持续未通过（风控拦截）：已恢复窗口到前台，"
                "请尝试在窗口里完成验证；若仍失败，可能是当前网络被风控，请稍后再试。"
            )
