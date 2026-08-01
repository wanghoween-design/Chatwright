"""通义千问网页版 Provider（www.qianwen.com）。

2026-08 实测校准：
  - 通义网页版已迁移到 www.qianwen.com（tongyi.aliyun.com 只是营销首页）
  - 游客模式即可对话（登录可同步历史）
  - 输入框：div[role='textbox']（contenteditable）
  - 回复气泡：.qk-markdown
"""

from __future__ import annotations

from playwright.async_api import Locator, Page

from .base import WebChatProvider

DEFAULT_URL = "https://www.qianwen.com/"


class QwenProvider(WebChatProvider):
    def __init__(self, page: Page, base_url: str = DEFAULT_URL):
        super().__init__(page, base_url)

    async def _after_open(self) -> None:
        # 万一被重定向到登录页，给个提示（游客模式一般不会）
        if "login" in self.page.url:
            print("[Chatwright] 通义千问检测到登录页，请先在浏览器中手动登录。")

    async def _type_and_submit(self, message: str) -> None:
        # 实测：输入框是 div[role='textbox']，不是 textarea
        box = self.page.locator("[role='textbox']").first
        await box.wait_for(state="visible", timeout=15000)
        await box.click()
        await box.fill(message)
        await self.page.keyboard.press("Enter")

    async def _bubbles(self) -> Locator:
        # 实测：回复内容在 .qk-markdown 里（欢迎语和每条回复各一个，last 取最新）
        return self.page.locator(
            ".qk-markdown, "
            "[class*='answer-common-card'], "
            "[class*='markdown-body']"
        )
