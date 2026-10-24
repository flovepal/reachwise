@echo off
rem Opens the public tunnel and reopens it if it drops.
setlocal EnableExtensions
call "%~dp0settings.bat"
if defined NGROK_EXE set NGROK_EXE=%NGROK_EXE:"=%
for %%I in ("%~dp0..") do set "BACKEND=%%~fI"
cd /d "%BACKEND%"
if not exist logs mkdir logs

if not defined NGROK_EXE if exist "%~dp0ngrok.exe" set "NGROK_EXE=%~dp0ngrok.exe"
if not defined NGROK_EXE if exist "%LOCALAPPDATA%\Microsoft\WindowsApps\ngrok.exe" set "NGROK_EXE=%LOCALAPPDATA%\Microsoft\WindowsApps\ngrok.exe"
if not defined NGROK_EXE for /f "delims=" %%P in ('where ngrok.exe 2^>nul') do if not defined NGROK_EXE set "NGROK_EXE=%%P"
if not defined NGROK_EXE (
  echo %date% %time% Could not find ngrok. Install it from the Microsoft Store or set NGROK_EXE in settings.bat. >> logs\ngrok.log
  exit /b 1
)

rem Give the network and the server a moment after sign-in
timeout /t 20 /nobreak > nul

:loop
if exist logs\ngrok.log for %%F in (logs\ngrok.log) do if %%~zF GTR 5000000 move /y logs\ngrok.log logs\ngrok.log.old > nul
echo %date% %time% Starting "%NGROK_EXE%" for https://%NGROK_DOMAIN% >> logs\ngrok.log
"%NGROK_EXE%" http --url=%NGROK_DOMAIN% %PORT% --log stdout >> logs\ngrok.log 2>&1
echo %date% %time% ngrok stopped (code %errorlevel%). Restarting in 15 seconds. >> logs\ngrok.log
timeout /t 15 /nobreak > nul
goto loop
