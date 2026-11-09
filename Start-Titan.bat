@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "TITAN_PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%TITAN_PS%" set "TITAN_PS=powershell.exe"
set "TITAN_SCRIPT=%~dp0Start-Titan.ps1"
"%TITAN_PS%" -NoProfile -ExecutionPolicy Bypass -File "%TITAN_SCRIPT%"
if errorlevel 1 (
  echo.
  echo Start-Titan failed. See the message above or run Start-Titan.ps1 in PowerShell for details.
  pause
)
