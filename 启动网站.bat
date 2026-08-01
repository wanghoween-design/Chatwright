@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto noenv

powershell -NoProfile -Command "$c=New-Object Net.Sockets.TcpClient; try{$c.Connect('127.0.0.1',8765);$c.Close();exit 0}catch{exit 1}"
if not errorlevel 1 goto already

echo 启动 Chatwright 服务中，稍候会自动打开浏览器...
echo 弹出的黑色窗口是服务窗口，请勿关闭，关闭即停止服务。
start "Chatwright Server" cmd /k ".venv\Scripts\python run_web.py"
exit /b 0

:already
echo 服务已在运行，正在打开浏览器...
start "" "http://127.0.0.1:8765"
exit /b 0

:noenv
echo [错误] 未找到 .venv\Scripts\python.exe
echo 请先在项目目录执行：
echo   python -m venv .venv
echo   .venv\Scripts\pip install -r requirements.txt
pause
exit /b 1
