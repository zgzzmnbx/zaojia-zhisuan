@echo off
setlocal
chcp 65001 >nul

set "PROJECT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%管勘智算启动器-【codex】.ps1"

echo.
echo 按任意键关闭本窗口。后端/前端服务窗口需要保持打开，关闭它们即停止程序。
pause >nul
