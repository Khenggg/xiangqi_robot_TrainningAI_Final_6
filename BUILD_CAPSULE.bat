@echo off
setlocal
cd /d "%~dp0"
rem Team/build machine only. Event machines use START.bat inside the release ZIP.
if exist ".venv312\Scripts\python.exe" (
  ".venv312\Scripts\python.exe" tools\capsule\build.py %*
) else (
  py -3.12 tools\capsule\build.py %*
)
exit /b %ERRORLEVEL%
