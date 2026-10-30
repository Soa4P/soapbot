@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo   soapbot - open the panel on this machine
echo ============================================================
echo.

set "PY=.venv\Scripts\python.exe"
set "LOG=data\panel.log"

if not exist "%PY%" (
    echo [1/4] no .venv here, creating one ...
    where py >nul 2>nul
    if %errorlevel%==0 (
        py -3 -m venv .venv
    ) else (
        python -m venv .venv
    )
    if not exist "%PY%" (
        echo.
        echo [x] Python was not found. Install Python 3.12 from python.org
        echo     and tick "Add python.exe to PATH" during setup.
        pause
        exit /b 1
    )
    echo       installing dependencies ...
    "%PY%" -m pip install --quiet --upgrade pip
    "%PY%" -m pip install --quiet -e .
)

if not exist "src\soapbot\webui\dist\index.html" (
    echo [x] the panel was never built: src\soapbot\webui\dist\index.html is missing.
    echo     build it once with:  cd webui ^&^& npm install ^&^& npm run build
    pause
    exit /b 1
)

if not exist ".env" (
    if exist ".env.example" (
        echo [i] no .env yet - copying .env.example
        copy /y ".env.example" ".env" >nul
    )
)

echo [2/4] starting the server on 127.0.0.1:6185 ...
set "SOAPBOT_HOST=127.0.0.1"
set "SOAPBOT_PORT=6185"
set "SOAPBOT_ENABLE_RUNTIME=true"
set "SOAPBOT_DATA_DIR=%CD%\data"
set "SOAPBOT_CONFIG_DIR=%CD%\config"
set "SOAPBOT_ENV_FILE=%CD%\.env"
if not exist "%SOAPBOT_DATA_DIR%" mkdir "%SOAPBOT_DATA_DIR%"

rem The log goes to a file, not to a minimised window: when the start fails the
rem reason has to be readable here, not hidden behind a taskbar icon.
start "soapbot panel" /min cmd /c ""%PY%" -m soapbot.cli start > "%LOG%" 2>&1"

echo [3/4] waiting for it to answer ...
set /a tries=0
:wait
set /a tries+=1
rem ping, not `timeout`: `timeout` refuses to run when stdin is redirected, which
rem turns a 2-second wait into a 0-second one and makes this loop useless.
ping -n 3 127.0.0.1 >nul
curl -s -o nul http://127.0.0.1:6185/api/health >nul 2>nul
if %errorlevel%==0 goto ready
if %tries% lss 15 goto wait

echo.
echo [x] it did not come up. Last lines of %LOG%:
echo ------------------------------------------------------------
if exist "%LOG%" (
    powershell -NoProfile -Command "Get-Content '%LOG%' -Tail 20" 2>nul
) else (
    echo   ^(no log was written - the process could not even start^)
)
echo ------------------------------------------------------------
echo.
echo   The usual cause is a missing secret: config\providers.yaml refers to
echo   a variable such as DEEPSEEK_API_KEY, and .env does not define it.
echo   Add the line to .env and run this again.
pause
exit /b 1

:ready
echo [4/4] up.
echo.
echo   panel:  http://127.0.0.1:6185
echo.
if exist "%SOAPBOT_DATA_DIR%\init_token.txt" (
    echo   login token ^(data\init_token.txt^), for a first run:
    type "%SOAPBOT_DATA_DIR%\init_token.txt"
    echo.
)
echo   Stop it with stop-panel.bat, or close the "soapbot panel" window.
echo.
start "" http://127.0.0.1:6185
ping -n 8 127.0.0.1 >nul
