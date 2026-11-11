@echo off
setlocal
cd /d "%~dp0"

if "%~1"=="" goto usage
if "%~2"=="" goto usage
if "%~3"=="" goto usage

set "HOST=%~1"
set "USER=%~2"
set "KEY=%~3"
set "SSH_PORT=%~4"
set "LOCAL_PORT=%~5"
set "REMOTE_PORT=%~6"
if not defined SSH_PORT set "SSH_PORT=22"
if not defined LOCAL_PORT set "LOCAL_PORT=6185"
if not defined REMOTE_PORT set "REMOTE_PORT=6185"

rem This file used to assemble the OpenSSH command line itself, expanding every
rem variable into one string that cmd parsed. A value containing &, |, > or a quote
rem then became part of the command instead of part of an argument.
rem Now it only forwards to scripts\connect-linux.ps1, which binds parameters
rem (PowerShell quotes them) and validates host, user and ports before ssh starts.
rem Keep it that way: no command construction in this file.

echo Connecting %USER%@%HOST%:%SSH_PORT%
echo Tunnel: localhost:%LOCAL_PORT% -^> server 127.0.0.1:%REMOTE_PORT%
start "soapbot tunnel" powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\connect-linux.ps1" -HostName "%HOST%" -User "%USER%" -KeyPath "%KEY%" -Port "%SSH_PORT%" -Tunnel -LocalPort "%LOCAL_PORT%" -RemotePort "%REMOTE_PORT%"
timeout /t 3 >nul
start "" "http://127.0.0.1:%LOCAL_PORT%"
echo.
echo Close the "soapbot tunnel" window to disconnect.
exit /b 0

:usage
echo Usage: open-remote-panel.bat HOST USER KEY_PATH [SSH_PORT] [LOCAL_PORT] [REMOTE_PORT]
echo Example: open-remote-panel.bat 203.0.113.10 ubuntu "%%USERPROFILE%%\.ssh\id_ed25519" 22 6185 6185
echo.
echo The panel stays on the Linux server's loopback and is reached through an SSH tunnel.
echo Ports default to 22 / 6185 / 6185. Same thing, without the bat:
echo   powershell -ExecutionPolicy Bypass -File scripts\connect-linux.ps1 -HostName HOST -User USER -KeyPath KEY -Tunnel
exit /b 2
