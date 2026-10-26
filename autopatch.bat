@echo off
setlocal
title Enshrouded mod autopatch
python -I "%~dp0tools\autopatch.py" apply
set "RC=%ERRORLEVEL%"

if "%~1"=="" (
    pause
    exit /b %RC%
)
if "%RC%"=="0" goto launch
if "%RC%"=="9009" (
    echo.
    echo Python was not found, so the mods were not checked. If the game was just updated,
    echo it may crash on world load; Steam "Verify integrity of game files" fixes that.
    pause
    goto launch
)
if "%RC%"=="1" (
    echo.
    echo The mods are not active this session. The game starts unmodded in 10 seconds.
    timeout /t 10
    goto launch
)
echo.
echo The game files are inconsistent and the game would likely crash on world load.
echo Run Steam "Verify integrity of game files" for Enshrouded, then start the game again.
pause
exit /b %RC%

:launch
%*
