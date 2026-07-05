@echo off
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -NoExit -Command "Set-Location -LiteralPath '%~dp0.'; python tools\archive_prd.py; Write-Host ''; Read-Host 'Press Enter to close'"
