@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHON_EXE=python"
if exist "%~dp0runtime\python\python.exe" set "PYTHON_EXE=%~dp0runtime\python\python.exe"
"%PYTHON_EXE%" backend\feishu_bot_runner.py
if errorlevel 1 pause
