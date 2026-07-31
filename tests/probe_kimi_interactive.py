"""Kimi 交互式探针：在首页输入一条消息，看真实的回复元素长什么样。

注意：Kimi 欢迎页（无登录态）通常允许发有限次数，体验完整会话仍需登录。
本脚本在未登录状态下尝试一次发送，用来发现回复气泡的真实选择器。
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from chatwright.browser import BrowserManager


async def main() -> None:
    bm = BrowserManager(headless=True)
    page = await bm.start()
    try:
        print("[1] 打开 Kimi…")
        await page.goto("https://kimi.moonshot.cn", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        print("[2] 输入测试消息…")
        box = page.locator(".chat-input-editor").first
        await box.wait_for(state="visible", timeout=10000)
        await box.click()
        await box.fill("你好，请用一句话介绍你自己")

        # 找发送按钮 — 先列出可见的 button
        buttons = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('button')).map(b => ({
                text: (b.innerText || '').trim().substring(0, 30),
                aria: b.getAttribute('aria-label') || '',
                cls: (b.className || '').toString().substring(0, 60),
                disabled: b.disabled,
            }));
        }""")
        print("    页面按钮:", buttons[:10])

        # 尝试按 Enter 发送（Kimi 通常支持 Enter）
        await page.keyboard.press("Enter")
        print("[3] 等回复…")
        await page.wait_for_timeout(8000)

        await page.screenshot(
            path=str(Path(__file__).resolve().parent / "probe_kimi_after.png"),
            full_page=True,
        )

        print("\n[4] 探测疑似回复气泡:")
        candidates = [
            "[class*='assistant']",
            "[class*='message']",
            "[class*='reply']",
            "[class*='markdown']",
            "[class*='answer']",
            "[class*='chat-item']",
            "[data-role='assistant']",
            "[data-author]",
            "[class*='bubble']",
            "[class*='response']",
        ]
        for sel in candidates:
            try:
                cnt = await page.locator(sel).count()
                if cnt > 0:
                    last_html = (await page.locator(sel).last.outer_html())[:300]
                    print(f"    {sel:45} count={cnt}   {last_html[:140]}")
            except Exception:
                pass

        # 找所有包含文字"我是Kimi"或类似内容的元素
        print("\n[5] 找含 'Kimi' 文字的元素:")
        kimis = await page.evaluate("""() => {
            const all = document.querySelectorAll('div, p, span');
            const hits = [];
            for (const el of all) {
                if (el.children.length < 5 && /Kimi|我是|助手/i.test(el.innerText || '')) {
                    hits.push({
                        tag: el.tagName,
                        cls: (el.className || '').toString().substring(0, 60),
                        text: (el.innerText || '').substring(0, 80),
                    });
                }
            }
            return hits.slice(0, 5);
        }""")
        for k in kimis:
            print(f"    {k}")

    finally:
        await bm.stop()


if __name__ == "__main__":
    asyncio.run(main())