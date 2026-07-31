"""Kimi 网页版 Provider（kimi.moonshot.cn）。

注意：选择器为 v0 启发式写法（与 deepseek.py 同状态），需登录后实测校准。
当前已知：
  - 输入框是 contenteditable div，不是 textarea，选择器 .chat-input-editor 已确认
  - 发送：Enter 键可用（探针实测）
  - 回复气泡：未登录态无回复，需先登录后才能继续校准
"""

from __future__ import annotations

from playwright.async_api import Locator, Page

from .base import WebChatProvider

DEFAULT_URL = "https://kimi.moonshot.cn"


class KimiProvider(WebChatProvider):
    def __init__(self, page: Page, base_url: str = DEFAULT_URL):
        super().__init__(page, base_url)

    async def _after_open(self) -> None:
        # Kimi 未登录时会弹出二维码登录框；headless 模式下需先用 login_any.py 手动登录
        modal = self.page.locator("text=微信扫码登录")
        if await modal.count() > 0:
            print("[Chatwright] Kimi 检测到登录弹窗，请先在浏览器中手动登录后重试。")

    async def _type_and_submit(self, message: str) -> None:
        # Kimi 输入框是 contenteditable div，不是 textarea
        box = self.page.locator(".chat-input-editor").first
        await box.wait_for(state="visible", timeout=15000)
        await box.click()
        await box.fill(message)
        # Kimi 支持 Enter 发送（探针实测可触发登录弹窗/后续发送）
        await self.page.keyboard.press("Enter")

    async def _bubbles(self) -> Locator:
        # 候选选择器，命中任一即可；登录后用 probe_kimi_interactive.py 重探校准
        return self.page.locator(
            "[data-message-role='assistant'], "
            "[class*='message-content'], "
            "[class*='chat-message'], "
            ".message-item .content, "
            "[class*='markdown-body']"
        )