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
    # 先释放 8765 端口：如果旧版服务还占着端口，bat 检测到"已在运行"会跳过启动，
    # 导致一直跑旧代码。这里自动结束占用进程，保证加载的是最新版本。
    try:
        import subprocess

        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=10).stdout
        pids = set()
        for line in out.splitlines():
            if ":8765" in line and "LISTENING" in line:
                parts = line.split()
                if parts and parts[-1].isdigit():
                    pids.add(parts[-1])
        for pid in pids:
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, timeout=10)
        if pids:
            print(f"[Chatwright] 已结束占用端口 8765 的旧进程（PID: {', '.join(sorted(pids))}），确保加载最新代码")
    except Exception:
        pass
    print("Chatwright Web UI 已启动 → http://127.0.0.1:8765")
    # 服务就绪后自动打开浏览器（设 CHATWRIGHT_NO_BROWSER=1 可关闭自动打开）
    if os.environ.get("CHATWRIGHT_NO_BROWSER") != "1":
        threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:8765")).start()
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
