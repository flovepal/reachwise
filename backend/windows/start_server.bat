@echo off
rem Starts the Reachwise server and restarts it if it ever stops.
setlocal EnableExtensions
call "%~dp0settings.bat"
rem Remove any quotes someone typed around the path
if defined PYTHON_EXE set PYTHON_EXE=%PYTHON_EXE:"=%
for %%I in ("%~dp0..") do set "BACKEND=%%~fI"
cd /d "%BACKEND%"
if not exist logs mkdir logs

if not defined PYTHON_EXE if exist "%BACKEND%\.venv\Scripts\python.exe" set "PYTHON_EXE=%BACKEND%\.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%BACKEND%\..\.venv\Scripts\python.exe" set "PYTHON_EXE=%BACKEND%\..\.venv\Scripts\python.exe"
if not defined PYTHON_EXE (
  echo %date% %time% Could not find .venv\Scripts\python.exe in %BACKEND%. >> logs\server.log
  exit /b 1
)

:loop
if exist logs\server.log for %%F in (logs\server.log) do if %%~zF GTR 5000000 move /y logs\server.log logs\server.log.old > nul
echo %date% %time% Starting server with "%PYTHON_EXE%" on port %PORT% >> logs\server.log
"%PYTHON_EXE%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT% --workers 1 >> logs\server.log 2>&1
echo %date% %time% Server stopped (code %errorlevel%). Restarting in 10 seconds. >> logs\server.log
timeout /t 10 /nobreak > nul
goto loop
