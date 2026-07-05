@echo off
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -NoExit -File "%~dp0tools\export_ai_review_bundle_window.ps1" -ProjectRoot "%~dp0."
