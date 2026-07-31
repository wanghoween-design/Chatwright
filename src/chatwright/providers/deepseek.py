"""DeepSeek 网页版 Provider（默认对接 chat.deepseek.com）。

注意：网页 AI 的 DOM 结构会随版本变化，下面选择器是 v0 启发式写法，
需按真实站点实测校准；这正是 v1「自愈层」要彻底解决的脆弱点。
"""

from __future__ import annotations

from playwright.async_api import Locator, Page

from .base import WebChatProvider

DEFAULT_URL = "https://chat.deepseek.com"


class DeepSeekProvider(WebChatProvider):
    def __init__(self, page: Page, base_url: str = DEFAULT_URL):
        super().__init__(page, base_url)

    async def _after_open(self) -> None:
        # 若跳转到登录页，等待用户在可见浏览器里手动登录（仅首次）
        if "login" in self.page.url or "sign_in" in self.page.url:
            print("[Chatwright] 检测到登录页，请在浏览器中手动登录，登录后自动继续…")
            # 登录成功后会跳回对话页
            await self.page.wait_for_url("**/chat**", timeout=0)

    async def _type_and_submit(self, message: str) -> None:
        box = self.page.locator("textarea").first
        await box.wait_for(state="visible", timeout=15000)
        await box.click()
        await box.fill(message)
        # DeepSeek 网页版支持 Enter 发送
        await self.page.keyboard.press("Enter")

    async def _bubbles(self) -> Locator:
        # 候选选择器，按真实 DOM 优先级匹配（命中任一即可）
        return self.page.locator(
            "[data-message-author-role='assistant'], "
            ".message-assistant, "
            ".ds-markdown, "
            "[class*='assistant']"
        )
