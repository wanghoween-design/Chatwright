"""端到端逻辑自测：不依赖真实账号 / 网络，验证整条对话流水线。

运行：
    cd Chatwright
    PYTHONPATH=src python tests/test_mock.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from chatwright.browser import BrowserManager
from chatwright.providers.mock import MockProvider

MOCK_HTML = Path(__file__).resolve().parent / "mock_chat.html"


async def main() -> None:
    bm = BrowserManager(headless=True)
    page = await bm.start()
    provider = MockProvider(page, base_url="file://" + str(MOCK_HTML))
    reply = await provider.send("你好，这是端到端自测")
    print("REPLY:", reply)
    assert "模拟回复" in reply, "mock 返回异常，流水线可能断裂"
    print("OK: Chatwright 端到端对话流水线跑通 ✅")
    await bm.stop()


if __name__ == "__main__":
    asyncio.run(main())
