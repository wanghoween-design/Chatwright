"""统一登录助手：手动登录一次，把登录态保存到对应平台的文件中。

用法（在 Chatwright 目录下）：
    .venv/Scripts/python tests/login_any.py deepseek
    .venv/Scripts/python tests/login_any.py kimi
    .venv/Scripts/python tests/login_any.py qwen

会打开可见浏览器窗口，请手动登录对应网页 AI（扫码/手机号等），
登录成功后回到终端按回车，登录态自动保存到 state/<平台>_storage.json。
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from chatwright.browser import BrowserManager
from chatwright.providers.deepseek import DEFAULT_URL as DEEPSEEK_URL
from chatwright.providers.kimi import DEFAULT_URL as KIMI_URL
from chatwright.providers.qwen import DEFAULT_URL as QWEN_URL

LOGIN_TARGETS = {
    "deepseek": ("chatwright_storage.json", DEEPSEEK_URL),
    "kimi":     ("kimi_storage.json",     KIMI_URL),
    "qwen":     ("qwen_storage.json",     QWEN_URL),
}


async def login(platform: str) -> None:
    if platform not in LOGIN_TARGETS:
        print(f"未知平台: {platform}; 可选: {list(LOGIN_TARGETS.keys())}")
        return

    state_filename, url = LOGIN_TARGETS[platform]
    bm = BrowserManager(headless=False, state_filename=state_filename)
    page = await bm.start()

    print(f"[1/3] 打开 {platform} ({url}) ...")
    await page.goto(url, wait_until="domcontentloaded")

    print(f"[2/3] 请在弹出的浏览器窗口中手动登录 {platform}（扫码/手机号等）...")
    print("      登录成功回到主界面后，回到终端按回车继续")
    input()

    print(f"[3/3] 保存登录态到 state/{state_filename} ...")
    await bm.save_state()
    print(f"OK: {platform} 登录态已保存。下次直接用 chat.py --{platform} 即可。")

    await bm.stop()


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in LOGIN_TARGETS:
        print("用法: .venv/Scripts/python tests/login_any.py <deepseek|kimi|qwen>")
        sys.exit(1)
    asyncio.run(login(sys.argv[1]))