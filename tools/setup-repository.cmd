@echo off
setlocal

where pwsh.exe >nul 2>nul
if not errorlevel 1 goto run_pwsh

where powershell.exe >nul 2>nul
if not errorlevel 1 goto run_windows_powershell

echo Setup failed: PowerShell was not found in PATH. 1>&2
exit /b 2

:run_pwsh
pwsh.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-repository.ps1"
exit /b %errorlevel%

:run_windows_powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-repository.ps1"
exit /b %errorlevel%
