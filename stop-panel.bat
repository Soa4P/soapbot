@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo Stopping the panel started by start-panel.bat ...

set "found=0"
for /f "tokens=2 delims=," %%p in ('tasklist /fi "imagename eq python.exe" /fo csv /nh 2^>nul') do (
    set "pid=%%~p"
    for /f "tokens=*" %%c in ('powershell -NoProfile -Command "(Get-CimInstance Win32_Process -Filter \"ProcessId=!pid!\").CommandLine" 2^>nul') do (
        echo %%c | findstr /i "soapbot.cli" >nul && (
            taskkill /pid !pid! /f >nul 2>nul
            echo   stopped pid !pid!
            set "found=1"
        )
    )
)

if "!found!"=="0" (
    echo   nothing was running. If a window titled "soapbot panel" is still open,
    echo   close it by hand - it is holding port 6185.
) else (
    echo   done.
)
timeout /t 5 >nul
