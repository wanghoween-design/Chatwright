"""Kimi 网页版 Provider（kimi.com）。

2026-08 实测：
  - 域名会跳转到 www.kimi.com
  - 输入框 .chat-input-editor 是 contenteditable div，偶尔被锁定为
    contenteditable=false（页面初始化中/登录引导），需点击激活或重试
  - 发送消息后若未登录，会弹出登录框，此时必须提示用户先登录
当前已知：
  - 回复气泡选择器需登录后校准
"""

from __future__ import annotations

from playwright.async_api import Locator, Page

from .base import WebChatProvider

DEFAULT_URL = "https://www.kimi.com/"


class KimiProvider(WebChatProvider):
    # Kimi 回复较慢，给足稳定期；消息区在 .message-list 里
    WAIT_STABLE: float = 5.0
    WAIT_MIN: float = 12.0

    def __init__(self, page: Page, base_url: str = DEFAULT_URL):
        super().__init__(page, base_url)

    async def _after_open(self) -> None:
        # Kimi 未登录时会弹出登录框；headless 模式下需先手动登录
        pass

    async def _type_and_submit(self, message: str) -> None:
        # Kimi 输入框是 contenteditable div，不是 textarea
        box = self.page.locator(".chat-input-editor").first
        await box.wait_for(state="visible", timeout=15000)
        # 编辑器在部分状态（初始化中/登录引导）下是 contenteditable=false，
        # 点击激活后重试 fill；多次失败则改用键盘逐字输入并校验文字确实进入
        last_err: Exception | None = None
        for _ in range(3):
            try:
                await box.click()
                await box.fill(message, timeout=5000)
                break
            except Exception as e:  # noqa: PERF203
                last_err = e
                await self.page.wait_for_timeout(1500)
        else:
            # 回退方案：聚焦后用键盘输入，并确认文字真的进去了
            await box.click()
            await self.page.keyboard.type(message, delay=15)
            typed = (await box.inner_text()).strip()
            if message not in typed:
                raise RuntimeError(
                    "Kimi 输入框当前不可编辑（可能未登录或引导弹窗未关闭）。"
                    "请在网页里先点击「去登录」完成登录后重试。"
                ) from last_err
        # Kimi 支持 Enter 发送（探针实测可触发登录弹窗/后续发送）
        await self.page.keyboard.press("Enter")

    async def _bubbles(self) -> Locator:
        # 候选选择器，命中任一即可；登录后需再实测校准
        return self.page.locator(
            "[data-message-role='assistant'], "
            "[class*='message-content'], "
            "[class*='chat-message'], "
            ".message-item .content, "
            "[class*='markdown-body']"
        )

    async def _message_container(self) -> str:
        return ".message-list"

    async def _check_interrupt(self) -> None:
        """发送后如果弹出登录框，说明必须登录才能对话，快速失败给用户明确提示。"""
        modal = (
            self.page.locator("[class*='login-modal']")
            .or_(self.page.locator("text=手机号登录"))
            .or_(self.page.locator("text=扫码登录"))
        )
        visible = await modal.count() > 0 and await modal.first.is_visible()
        # 宽限期：Kimi 打开页面会先闪登录界面，1-2 秒后自动登录，不能立即判定失败
        if self._modal_persisted(visible):
            raise RuntimeError(
                "Kimi 需要先登录才能对话：请点击页面上 Kimi 卡片里的「去登录」，"
                "在弹出的浏览器窗口完成登录后再试。"
            )
