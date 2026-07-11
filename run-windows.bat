@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-windows.ps1" %*
exit /b %ERRORLEVEL%