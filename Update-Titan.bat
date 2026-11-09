@echo off
setlocal
cd /d "%~dp0"
echo.
echo Project Titan - Update
echo   Pull origin/main, refresh deps when needed, start Operations Center
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Update-Titan.ps1"
if errorlevel 1 (
  echo.
  echo Update-Titan failed. Read the red message above, then press Enter in that window.
  pause
  exit /b 1
)
