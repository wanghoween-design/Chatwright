"""快速测试：用已保存的登录态直接向 DeepSeek 发一条消息。

运行：
    cd Chatwright
    set PLAYWRIGHT_BROWSERS_PATH=%cd%\.pw-browsers
    .venv\Scripts\python tests\run_deepseek.py
"""

import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from chatwright.browser import BrowserManager
from chatwright.providers.deepseek import DeepSeekProvider


async def main() -> None:
    print("[1/4] 启动浏览器（使用已保存的登录态）...")
    bm = BrowserManager(headless=False)
    page = await bm.start()

    print("[2/4] 打开 DeepSeek 并发送消息...")
    provider = DeepSeekProvider(page)
    try:
        reply = await provider.send("你好，请用一句话介绍你自己", timeout=60)
        print(f"[3/4] 收到回复:\n{'─' * 40}\n{reply}\n{'─' * 40}")
    except Exception as e:
        print(f"[错误] 对话失败: {e}")
        # 截图方便调试
        screenshot = Path(__file__).resolve().parent / "debug_deepseek_error.png"
        await page.screenshot(path=str(screenshot), full_page=True)
        print(f"[调试] 截图已保存到: {screenshot}")

    print("[4/4] 关闭浏览器")
    await bm.stop()


if __name__ == "__main__":
    asyncio.run(main())
