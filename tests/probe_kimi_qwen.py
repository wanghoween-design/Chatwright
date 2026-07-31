"""Kimi + 通义千问 DOM 探针：打开每个站点，打印输入框和助手回复元素的真实结构。

运行：
    cd Chatwright
    set PLAYWRIGHT_BROWSERS_PATH=%cd%.pw-browsers
    .venv\Scripts\python tests\probe_kimi_qwen.py
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from chatwright.browser import BrowserManager


async def probe(name: str, url: str) -> dict:
    print(f"\n{'='*60}\n  [{name}] {url}\n{'='*60}")
    bm = BrowserManager(headless=True)
    page = await bm.start()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)
    except Exception as e:
        print(f"  [跳过] 无法访问: {e}")
        shot = Path(__file__).resolve().parent / f"probe_{name}_fail.png"
        await page.screenshot(path=str(shot), full_page=True)
        await bm.stop()
        return {"name": name, "error": str(e)}

    # 截图
    shot = Path(__file__).resolve().parent / f"probe_{name}.png"
    await page.screenshot(path=str(shot), full_page=True)
    print(f"  截图: {shot}")

    # 探测输入元素
    print("  --- 输入元素 ---")
    inputs = await page.evaluate("""() => {
        const els = document.querySelectorAll(
          'textarea, input[type="text"], [contenteditable="true"], [role="textbox"]'
        );
        return Array.from(els).slice(0, 5).map(el => ({
            tag: el.tagName,
            id: el.id || '',
            class: (el.className || '').toString().substring(0, 80),
            placeholder: (el.placeholder || '').substring(0, 60),
            role: el.getAttribute('role') || '',
            'aria-label': el.getAttribute('aria-label') || '',
            type: el.getAttribute('type') || '',
        }));
    }""")
    for inp in inputs:
        print(f"    {inp}")

    # 探测可能的助手回复气泡
    print("  --- 疑似助手回复气泡（候选选择器命中数）---")
    candidates = [
        "[class*='assistant']",
        "[class*='reply']",
        "[class*='message']",
        "[class*='answer']",
        "[class*='chat-bubble']",
        "[class*='markdown']",
        "[data-role='assistant']",
        "[data-author*='assistant']",
        "[class*='ai-msg']",
        "[class*='bot']",
        "main",
    ]
    for sel in candidates:
        try:
            cnt = await page.locator(sel).count()
            if cnt > 0:
                # 最后一个元素的 class + 前 200 字
                last_html = (await page.locator(sel).last.outer_html())[:250]
                print(f"    {sel:45} count={cnt}   {last_html[:120]}")
        except Exception:
            pass

    await bm.stop()
    return {"name": name, "inputs": inputs}


async def main() -> None:
    await probe("kimi", "https://kimi.moonshot.cn")
    await probe("qwen", "https://tongyi.aliyun.com")


if __name__ == "__main__":
    asyncio.run(main())
