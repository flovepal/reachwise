@echo off
rem ---- Reachwise lab-PC settings ----
rem You normally don't need to change anything here. Python and ngrok are found automatically.
rem If you do fill in a path, write it WITHOUT quotes, like:  set PYTHON_EXE=C:\Users\user\...\python.exe

set NGROK_DOMAIN=savanna-unparallel-nonenigmatically.ngrok-free.dev
set PORT=8000

rem Leave empty to find automatically (works with the Microsoft Store version of ngrok)
set NGROK_EXE=

rem Leave empty to use backend\.venv automatically
set PYTHON_EXE=

rem This folder's own overrides (not uploaded to GitHub), e.g. a different PORT for production
if exist "%~dp0settings.local.bat" call "%~dp0settings.local.bat"
