@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0apply_do_patch.ps1" -Root "%~dp0."
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" echo Patch failed. Check the folder and message above.
pause
exit /b %RC%
