"""腾讯元宝网页版 Provider（yuanbao.tencent.com）。

2026-08 实测：
  - 输入框：.ql-editor（Quill 富文本编辑器，contenteditable div）
  - 未登录时输入框被禁用，并自动弹出微信扫码登录框（.hyc-login）
  - 必须先微信 / 手机 / QQ 登录后才能对话
  - 回复气泡选择器需登录后校准
"""

from __future__ import annotations

from playwright.async_api import Locator, Page

from .base import WebChatProvider

DEFAULT_URL = "https://yuanbao.tencent.com/chat/"


class YuanbaoProvider(WebChatProvider):
    def __init__(self, page: Page, base_url: str = DEFAULT_URL):
        super().__init__(page, base_url)

    async def _after_open(self) -> None:
        # 未登录时会自动弹出微信扫码登录框
        pass

    async def _type_and_submit(self, message: str) -> None:
        box = self.page.locator(".ql-editor").first
        await box.wait_for(state="visible", timeout=15000)
        await box.click()
        await box.fill(message)
        await self.page.keyboard.press("Enter")

    async def _bubbles(self) -> Locator:
        # 候选选择器，登录后需实测校准
        return self.page.locator(
            "[class*='message'], "
            "[class*='markdown'], "
            "[class*='assistant'], "
            "[class*='answer']"
        )

    async def _check_interrupt(self) -> None:
        """发送后若弹出微信扫码登录框，快速失败并提示用户先登录。"""
        modal = self.page.locator("[class*='hyc-login']").or_(
            self.page.locator("text=请使用微信扫描二维码登录")
        )
        if await modal.count() > 0 and await modal.first.is_visible():
            raise RuntimeError(
                "元宝需要登录才能对话：请点击页面上元宝卡片里的「去登录」，"
                "在弹出窗口里用微信 / 手机 / QQ 完成登录后重试。"
            )
