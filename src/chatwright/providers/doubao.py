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
    WAIT_STABLE: float = 5.0
    WAIT_MIN: float = 12.0

    def _prefer_census(self) -> bool:
        return True  # 豆包回复容器类名不固定，优先用全页文字普查

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
        # 实测：豆包 Enter 只会清空输入框、不会真正发送，必须点发送按钮
        btn = self.page.locator(".send-btn-wrapper").first
        if await btn.count() and await btn.is_visible():
            await btn.click()
        else:
            await self.page.keyboard.press("Enter")
        # 保险：点击后输入框仍没清空则再按一次 Enter
        await self.page.wait_for_timeout(1200)
        if (await box.input_value()).strip():
            await self.page.keyboard.press("Enter")

    async def _bubbles(self) -> Locator:
        # 候选选择器，登录后需实测校准
        return self.page.locator("[class*='markdown'], [class*='message'], [class*='answer']")

    async def _message_container(self) -> str:
        return "[class*='message']"

    async def _check_interrupt(self) -> None:
        if "region-ban" in self.page.url:
            raise RuntimeError(
                "豆包当前网络受区域限制（页面提示请先登录再使用）。"
                "请点击豆包卡片里的「去登录」，在浏览器窗口里登录后重试。"
            )
        # 图片/滑块类验证码：需要人工在窗口里完成
        for text in ("安全验证", "请完成验证", "点击图中", "请依次点击", "按住滑块"):
            loc = self.page.locator(f"text={text}")
            n = await loc.count()
            for i in range(n):
                try:
                    if await loc.nth(i).is_visible():
                        await self._restore_window()
                        raise RuntimeError(
                            "豆包弹出验证码（图片/滑块类）：已恢复豆包窗口到前台，"
                            "请在弹出的窗口里按提示完成验证，完成后重新发送消息。"
                        )
                except RuntimeError:
                    raise
                except Exception:
                    continue
        # 未登录检测：只认真正的登录弹窗（页面常驻的「登录」按钮会误判，
        # 实测已登录状态下页面也有「登录」按钮）
        dialog = (
            self.page.locator("[role='dialog'], [class*='login-modal'], [class*='passport']")
            .or_(self.page.locator("text=扫码登录"))
            .or_(self.page.locator("text=手机号登录"))
        )
        visible = await dialog.count() > 0 and await dialog.first.is_visible()
        # 宽限期：豆包打开页面也可能先闪登录界面再自动登录
        if self._modal_persisted(visible):
            raise RuntimeError(
                "豆包需要登录才能对话：登录态在重启服务后会失效，"
                "请点击豆包卡片里的「去登录」重新登录"
                "（登录后窗口会最小化保活，请勿关闭任务栏里的窗口）。"
            )
