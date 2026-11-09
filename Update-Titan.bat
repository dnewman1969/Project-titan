@echo off
setlocal
cd /d "%~dp0"
echo.
echo Project Titan - Update (pull main, then start)
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Update-Titan.ps1"
if errorlevel 1 (
  echo.
  echo Update-Titan failed. See the message above.
  pause
  exit /b 1
)
