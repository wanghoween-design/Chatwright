"""交互式终端对话：直接在 terminal 里和网页 AI 聊天。

用法（在 Chatwright 目录下）：
    # 先设置浏览器路径（Windows）
    set PLAYWRIGHT_BROWSERS_PATH=%cd%.pw-browsers

    # 选择平台（默认 deepseek）
    .venv/Scripts/python chat.py             # DeepSeek
    .venv/Scripts/python chat.py --kimi      # Kimi
    .venv/Scripts/python chat.py --qwen      # 通义千问
    .venv/Scripts/python chat.py --mock      # 本地演示（无需登录）

对话方式：终端输入消息按回车发送；输入 exit / quit / 退出 结束。

首次使用新平台：先运行 .venv/Scripts/python tests/login_any.py <平台名> 手动登录一次，
登录态会自动保存到 state/<平台>_storage.json，下次直接用即可。
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from chatwright.browser import BrowserManager
from chatwright.providers.deepseek import DeepSeekProvider
from chatwright.providers.qwen import QwenProvider
from chatwright.providers.doubao import DoubaoProvider
from chatwright.providers.yuanbao import YuanbaoProvider
from chatwright.providers.zhipu import ZhipuProvider

# 平台注册表：name -> (Provider 类, 登录态文件名, 描述, 特殊 URL 构造)
PLATFORMS = {
    "deepseek": (DeepSeekProvider, "deepseek_storage.json", "DeepSeek 网页版", None),
    "qwen":     (QwenProvider,     "qwen_storage.json",     "通义千问 网页版", None),
    "doubao":   (DoubaoProvider,   "doubao_storage.json",   "豆包 网页版",       None),
    "yuanbao":  (YuanbaoProvider,  "yuanbao_storage.json",  "元宝 网页版",       None),
    "zhipu":    (ZhipuProvider,    "zhipu_storage.json",    "智谱 网页版",       None),
}


def pick_platform(argv):
    for arg in argv[1:]:
        if arg.startswith("--") and arg[2:] in PLATFORMS:
            return arg[2:]
    return "deepseek"


async def main(platform: str) -> None:
    cls, state_filename, desc, special_url = PLATFORMS[platform]

    if state_filename:
        bm = BrowserManager(headless=True, state_filename=state_filename)
    else:
        bm = BrowserManager(headless=True)
    page = await bm.start()

    if special_url:
        provider = cls(page, base_url=special_url)
    else:
        provider = cls(page)

    print(f"=== {desc}（{platform}）===")
    if state_filename:
        if bm.state_path.exists():
            print(f"[已用登录态] {bm.state_path}")
        else:
            print(f"[提示] 未发现登录态，请先运行 .venv/Scripts/python tests/login_any.py {platform} 手动登录一次")
    print("输入消息回车发送；exit / quit / 退出 结束。\n")

    while True:
        try:
            msg = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见")
            break
        if msg.lower() in ("exit", "quit", "退出", "q"):
            print("再见")
            break
        if not msg:
            continue
        try:
            reply = await provider.send(msg, timeout=120)
        except Exception as e:
            print(f"[出错] {e}\n")
            continue
        print("AI>", reply, "\n")

    await bm.stop()


if __name__ == "__main__":
    asyncio.run(main(pick_platform(sys.argv)))
