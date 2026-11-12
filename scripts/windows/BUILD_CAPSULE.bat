@echo off
setlocal
for %%I in ("%~dp0..\..") do set "XQ_ROOT=%%~fI\"
cd /d "%XQ_ROOT%"
rem Team/build machine only. Event machines use START.bat inside the release ZIP.
if exist ".venv312\Scripts\python.exe" (
  ".venv312\Scripts\python.exe" tools\capsule\build.py %*
) else (
  py -3.12 tools\capsule\build.py %*
)
exit /b %ERRORLEVEL%
