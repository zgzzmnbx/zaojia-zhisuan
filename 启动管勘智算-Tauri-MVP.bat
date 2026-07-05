@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title GuanKanZhiSuan Tauri MVP

echo Starting GuanKanZhiSuan Tauri MVP...
echo Project: %CD%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\run_tauri.ps1" dev
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%EXIT_CODE%"=="0" (
  echo [ERROR] Tauri startup failed. Exit code: %EXIT_CODE%
  echo Please copy the output above and send it to Codex.
) else (
  echo Tauri dev process exited.
)
echo.
pause
exit /b %EXIT_CODE%
