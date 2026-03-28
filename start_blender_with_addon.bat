@echo off
setlocal
:: Targeted Cleanup: Kill previous development consoles using robust PowerShell matching
powershell -Command "Get-Process cmd | Where-Object { $_.MainWindowTitle -like '*FCD_BLENDER_DEV_CONSOLE*' } | Stop-Process -Force -ErrorAction SilentlyContinue"
taskkill /F /IM blender.exe /T 2>nul

:: Set a unique title for the current session to allow cleanup on the next run
title FCD_BLENDER_DEV_CONSOLE

:: Unblock files that might be restricted because they were downloaded from the internet (GitHub)
powershell -ExecutionPolicy Bypass -Command "Get-ChildItem -Path '%~dp0' -Recurse | Unblock-File"

:: Running through Python to avoid Smart App Control blocks on complex batch logic
python "%~dp0dev_tool.py" start
if %ERRORLEVEL% NEQ 0 pause
