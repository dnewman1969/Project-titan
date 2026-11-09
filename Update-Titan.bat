@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo.
echo Project Titan - Update
echo   Pull origin/main, refresh deps when needed, start Operations Center
echo.
set "TITAN_PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%TITAN_PS%" set "TITAN_PS=powershell.exe"
set "TITAN_SCRIPT=%~dp0Update-Titan.ps1"
"%TITAN_PS%" -NoProfile -ExecutionPolicy Bypass -File "%TITAN_SCRIPT%"
if errorlevel 1 (
  echo.
  echo Update-Titan failed. Read the red message above, then press Enter in that window.
  pause
  exit /b 1
)
