@echo off
setlocal
set "SCRIPT=%~dp0scripts\manage_codexbridge_service.ps1"
if not exist "%SCRIPT%" (
  echo [ERROR] Service controller not found: %SCRIPT%
  exit /b 1
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
exit /b %ERRORLEVEL%
