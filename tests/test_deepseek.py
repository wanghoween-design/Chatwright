"""对接真实 DeepSeek 网页的端到端测试。

首次运行会打开浏览器窗口，需要你手动登录 DeepSeek，
登录成功后脚本会自动继续发送消息。

运行：
    cd Chatwright
    PYTHONPATH=src python tests/test_deepseek.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from chatwright.browser import BrowserManager


async def main() -> None:
    # headless=False → 显示浏览器窗口（首次必须，方便手动登录）
    bm = BrowserManager(headless=False)
    page = await bm.start()

    # 打开 DeepSeek
    await page.goto("https://chat.deepseek.com", wait_until="domcontentloaded")

    # 等你手动登录完成——在终端按回车继续
    input("[Chatwright] 请在浏览器中完成登录，登录成功后回到终端按回车继续…")

    # 按回车后暂停 3 秒，等页面完全加载
    await page.wait_for_timeout(3000)

    # 截图保存，方便查看登录后的页面状态
    screenshot_path = Path(__file__).resolve().parent / "debug_after_login.png"
    await page.screenshot(path=str(screenshot_path), full_page=True)
    print(f"[调试] 截图已保存到: {screenshot_path}")

    # 打印页面上所有可交互元素，帮你找到输入框的真实选择器
    elements = await page.evaluate("""() => {
        const inputs = document.querySelectorAll('textarea, input[type="text"], [contenteditable="true"], [role="textbox"]');
        return Array.from(inputs).map(el => ({
            tag: el.tagName,
            id: el.id,
            class: el.className,
            placeholder: el.placeholder || '',
            role: el.getAttribute('role') || ''
        }));
    }""")
    print("[调试] 页面上的输入元素:", elements)

    # 登录成功后，取消下面这行的注释，保存登录态供下次复用
    await bm.save_state()
    print("登录态已保存，下次启动不用再手动登录")

    await bm.stop()


if __name__ == "__main__":
    asyncio.run(main())
