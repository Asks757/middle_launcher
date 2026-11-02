@echo off
rem Start Middle Launcher without a console window
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "%~dp0app.py"
) else (
    echo Please run install_windows.bat first.
    pause
)
