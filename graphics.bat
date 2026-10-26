@echo off
where pythonw >nul 2>nul && (start "" pythonw -I "%~dp0tools\gfxgui.py" & exit /b 0)
python -I "%~dp0tools\gfxgui.py"
if errorlevel 1 pause
