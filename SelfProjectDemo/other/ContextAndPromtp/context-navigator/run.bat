@echo off
chcp 65001 >nul
cd /d %~dp0
echo 启动 Context Navigator ...
python -m uvicorn app.main:app --port 8765
pause
