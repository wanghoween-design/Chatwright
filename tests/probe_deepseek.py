"""探针：用已保存登录态跑真实 DeepSeek，打印回复元素的真实 DOM 结构，用于校准选择器。

运行：
    cd Chatwright
    set PLAYWRIGHT_BROWSERS_PATH=%cd%.pw-browsers
    .venv\Scripts\python tests\probe_deepseek.py
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from chatwright.browser import BrowserManager
from chatwright.providers.deepseek import DeepSeekProvider


async def main() -> None:
    print("[1] 启动浏览器（复用已保存登录态）...")
    bm = BrowserManager(headless=True)
    page = await bm.start()

    prov = DeepSeekProvider(page)
    try:
        print("[2] 发送消息并等待回复...")
        reply = await prov.send("你好，请用一句话介绍你自己", timeout=45)
        print("[OK] 抓到回复:\n" + "─" * 40)
        print(reply)
        print("─" * 40)
    except Exception as e:
        print("[ERROR]", repr(e))
        print("\n[诊断] 逐个候选选择器探测真实 DOM:")
        candidates = [
            "[data-message-author-role='assistant']",
            ".message-assistant",
            ".ds-markdown",
            "[class*='assistant']",
            "[class*='message']",
            "[data-message-id]",
            "[class*='bubble']",
            "[class*='chat']",
            "main",
            "[role='presentation']",
        ]
        for sel in candidates:
            try:
                cnt = await page.locator(sel).count()
                print(f"  {sel!r:55} -> count={cnt}")
                if cnt:
                    html = await page.locator(sel).last.outer_html()
                    print("      HTML:", html[:600].replace("\n", " "))
            except Exception as ex:
                print(f"  {sel!r:55} -> ERR {ex}")
        shot = Path(__file__).resolve().parent / "probe_error.png"
        await page.screenshot(path=str(shot), full_page=True)
        print(f"\n[调试] 截图已存: {shot}")
    finally:
        await bm.stop()


if __name__ == "__main__":
    asyncio.run(main())
