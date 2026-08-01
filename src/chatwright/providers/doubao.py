"""豆包网页版 Provider（www.doubao.com）。

2026-08 实测：
  - 部分网络访问 www.doubao.com/chat/ 会进入区域限制页
    （/security/doubao-region-ban），页面提供「登录」入口
  - 输入框选择器为启发式写法（textarea / contenteditable / role=textbox），
    需登录后实测校准
"""

from __future__ import annotations

from playwright.async_api import Locator, Page

from .base import WebChatProvider

DEFAULT_URL = "https://www.doubao.com/chat/"


class DoubaoProvider(WebChatProvider):
    def __init__(self, page: Page, base_url: str = DEFAULT_URL):
        super().__init__(page, base_url)

    async def _after_open(self) -> None:
        if "region-ban" in self.page.url:
            print("[Chatwright] 豆包当前网络受区域限制，页面提示请先登录再使用豆包。")

    async def _type_and_submit(self, message: str) -> None:
        # 实测：页面里有两个 textarea，第一个是隐藏的，必须选可见的那个
        box = self.page.locator("textarea:visible").first
        await box.wait_for(state="visible", timeout=15000)
        await box.click()
        await box.fill(message)
        await self.page.keyboard.press("Enter")

    async def _bubbles(self) -> Locator:
        # 候选选择器，登录后需实测校准
        return self.page.locator("[class*='markdown'], [class*='message'], [class*='answer']")

    async def _check_interrupt(self) -> None:
        if "region-ban" in self.page.url:
            raise RuntimeError(
                "豆包当前网络受区域限制（页面提示请先登录再使用）。"
                "请点击豆包卡片里的「去登录」，在浏览器窗口里登录后重试。"
            )
