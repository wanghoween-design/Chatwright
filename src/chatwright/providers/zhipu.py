"""智谱清言 ChatGLM 网页版 Provider（chatglm.cn）。

2026-08 实测：
  - 游客模式即可对话（有次数/积分限制，登录可解锁更多功能）
  - 输入框：textarea
  - 回复气泡：.markdown-body（AI 回复内容）
"""

from __future__ import annotations

from playwright.async_api import Locator, Page

from .base import WebChatProvider

DEFAULT_URL = "https://chatglm.cn/main/all"


class ZhipuProvider(WebChatProvider):
    def __init__(self, page: Page, base_url: str = DEFAULT_URL):
        super().__init__(page, base_url)

    async def _after_open(self) -> None:
        if "login" in self.page.url:
            print("[Chatwright] 智谱检测到登录页，请在浏览器中手动登录。")

    async def _type_and_submit(self, message: str) -> None:
        box = self.page.locator("textarea").first
        await box.wait_for(state="visible", timeout=15000)
        await box.click()
        await box.fill(message)
        await self.page.keyboard.press("Enter")

    async def _bubbles(self) -> Locator:
        # 实测：AI 回复在 .markdown-body 里（.answer-content-wrap 是外层容器）
        return self.page.locator(".markdown-body, [class*='answer-content-wrap']")
