@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   soapbot - open the panel running on the server
echo ============================================================
echo.
echo   Server : root@189.105.68.245   (ssh on port 443; port 22 is blocked here)
echo   Key    : %USERPROFILE%\.ssh\soapbot_deploy
echo   Tunnel : localhost:6185  ->  server 127.0.0.1:6185
echo.
echo   The panel on the server listens on its own loopback only, so a tunnel
echo   is the intended way in - not a workaround around something unfinished.
echo.

where ssh >nul 2>nul
if errorlevel 1 (
    echo [x] ssh.exe not found. It ships with Windows 10/11 as "OpenSSH Client".
    pause
    exit /b 1
)

if not exist "%USERPROFILE%\.ssh\soapbot_deploy" (
    echo [x] private key not found: %USERPROFILE%\.ssh\soapbot_deploy
    pause
    exit /b 1
)

start "soapbot tunnel" ssh -p 443 -i "%USERPROFILE%\.ssh\soapbot_deploy" -N -L 6185:127.0.0.1:6185 root@189.105.68.245
echo   tunnel window opened, waiting for it to come up ...
timeout /t 6 >nul

start "" http://127.0.0.1:6185
echo.
echo   Close the "soapbot tunnel" window to disconnect.
timeout /t 10 >nul
