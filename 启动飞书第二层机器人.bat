@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHON_EXE=python"
if exist "%~dp0runtime\python\python.exe" set "PYTHON_EXE=%~dp0runtime\python\python.exe"
"%PYTHON_EXE%" -c "from backend.app.feishu_app_bot import start_enabled_bot_processes; print(start_enabled_bot_processes())"
if errorlevel 1 pause
