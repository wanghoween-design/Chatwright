"""一键启动 Chatwright Web UI。

用法（在 Chatwright 项目根目录）：
    .venv\\Scripts\\python run_web.py
然后浏览器打开 http://127.0.0.1:8765
"""

import os
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

# 自动指向项目自带的 Playwright 浏览器目录（如果存在），避免依赖全局安装
if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
    bundled = ROOT / ".pw-browsers"
    if bundled.exists():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(bundled)

try:
    import uvicorn  # noqa: E402
    from chatwright.webapp import app  # noqa: E402
except ImportError:
    print("缺少依赖，请先执行：.venv\\Scripts\\pip install -r requirements.txt")
    sys.exit(1)

if __name__ == "__main__":
    print("Chatwright Web UI 已启动 → http://127.0.0.1:8765")
    # 服务就绪后自动打开浏览器（设 CHATWRIGHT_NO_BROWSER=1 可关闭自动打开）
    if os.environ.get("CHATWRIGHT_NO_BROWSER") != "1":
        threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:8765")).start()
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
