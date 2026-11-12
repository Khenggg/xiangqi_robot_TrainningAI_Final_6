@echo off
setlocal
for %%I in ("%~dp0..\..") do set "XQ_ROOT=%%~fI\"
cd /d "%XQ_ROOT%"
rem Team/build machine only: builds Xiangqi-FR3.zip at the project root.
rem Example: scripts\windows\BUILD_XIANGQI_FR3.bat --models "D:\path\to\models" [--force]
if exist "%XQ_ROOT%.venv312\Scripts\python.exe" (
  "%XQ_ROOT%.venv312\Scripts\python.exe" tools\installer\build_zip.py %*
) else (
  py -3.12 tools\installer\build_zip.py %*
)
exit /b %ERRORLEVEL%
