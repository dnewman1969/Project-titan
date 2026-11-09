@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Titan.ps1"
if errorlevel 1 (
  echo.
  echo Start-Titan failed. See the message above or run Start-Titan.ps1 in PowerShell for details.
  pause
)
