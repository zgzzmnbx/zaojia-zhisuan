@echo off
setlocal
chcp 65001 >nul

set "PROJECT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%管勘智算启动器-【codex】.ps1" -StatusOnly

echo.
echo 按任意键关闭本窗口。
pause >nul
