@echo off
setlocal
cd /d "%~dp0"
echo ==============================================
echo   Middle Launcher - Windows installer
echo ==============================================
echo.

set "PY="
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>nul
    if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 (
        python -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>nul
        if not errorlevel 1 set "PY=python"
    )
)
if not defined PY (
    where python3 >nul 2>nul
    if not errorlevel 1 (
        python3 -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>nul
        if not errorlevel 1 set "PY=python3"
    )
)
if not defined PY (
    echo [X] Python 3.9+ not found.
    echo     Download: https://www.python.org/downloads/
    echo     Remember to check "Add python.exe to PATH" when installing.
    pause
    exit /b 1
)

if exist ".venv\Scripts\python.exe" (
    echo [1/3] Virtual environment exists, skipped.
) else (
    echo [1/3] Creating virtual environment...
    %PY% -m venv .venv
    if errorlevel 1 ( echo [X] venv creation failed & pause & exit /b 1 )
)

echo [2/3] Installing dependencies ~100MB, please wait...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo     Retrying with a faster mirror...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple
)
if errorlevel 1 ( echo [X] Dependency installation failed. & pause & exit /b 1 )

echo [3/3] Creating desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\make_shortcut.ps1" -AppDir "%~dp0." -Target "%~dp0.venv\Scripts\pythonw.exe"

echo.
echo Starting Middle Launcher...
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0app.py"
echo.
echo Done. Hold the middle mouse button for 0.3s to open the menu.
echo Tray icon: open menu / edit config / start with Windows / quit.
pause
