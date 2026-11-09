@echo off
setlocal
cd /d "%~dp0\.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-memurai-titan.ps1" %*
if errorlevel 1 (
  echo.
  echo setup-memurai-titan failed. Run this .bat as Administrator if Memurai did not restart.
  pause
)
