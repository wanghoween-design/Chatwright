"""通义千问网页版 Provider（tongyi.aliyun.com）。

注意：选择器为 v0 启发式写法（与 deepseek.py 同状态），需登录后实测校准。
当前已知：
  - 首页未登录态会被登录墙挡住，输入元素探测为 0
  - 登录后输入通常为 textarea；具体选择器需用 probe_any.py 实测
"""

from __future__ import annotations

from playwright.async_api import Locator, Page

from .base import WebChatProvider

DEFAULT_URL = "https://tongyi.aliyun.com"


class QwenProvider(WebChatProvider):
    def __init__(self, page: Page, base_url: str = DEFAULT_URL):
        super().__init__(page, base_url)

    async def _after_open(self) -> None:
        # 通义千问首页未登录时跳到登录页
        if "login" in self.page.url or "sign" in self.page.url:
            print("[Chatwright] 通义千问检测到登录页，请先在浏览器中手动登录。")

    async def _type_and_submit(self, message: str) -> None:
        # 通义千问输入框通常是 textarea（基于常见模式，待登录后实测确认）
        box = self.page.locator("textarea").first
        await box.wait_for(state="visible", timeout=15000)
        await box.click()
        await box.fill(message)
        await self.page.keyboard.press("Enter")

    async def _bubbles(self) -> Locator:
        # 候选选择器，登录后用 probe_qwen_interactive.py 校准
        return self.page.locator(
            "[data-role='assistant'], "
            "[class*='message-body'], "
            "[class*='markdown-body'], "
            "[class*='chat-message'], "
            "[class*='answer']"
        )