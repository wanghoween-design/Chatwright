"""Mock Provider —— 用于无登录、无网络的本地演示与端到端逻辑自测。

它对接 tests/mock_chat.html：一个纯前端的"假网页 AI"，点击发送后逐字流式输出。
selector 与基类通用轮询完全兼容，因此可以验证整条对话流水线而不依赖真实账号。
"""

from __future__ import annotations

from playwright.async_api import Locator, Page

from .base import WebChatProvider


class MockProvider(WebChatProvider):
    def __init__(self, page: Page, base_url: str):
        super().__init__(page, base_url)

    async def _type_and_submit(self, message: str) -> None:
        box = self.page.locator("#input").first
        await box.wait_for(state="visible", timeout=5000)
        await box.fill(message)
        await self.page.locator("#send").click()

    async def _bubbles(self) -> Locator:
        return self.page.locator(".reply")
