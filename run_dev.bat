@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "PYTHON_EXE=%PROJECT_DIR%.venv\Scripts\python.exe"
set "WEBSITE_DIR=%PROJECT_DIR%website"

if not exist "%PYTHON_EXE%" (
    echo Error: Python virtual environment was not found.
    echo Expected: %PYTHON_EXE%
    pause
    exit /b 1
)

if not exist "%WEBSITE_DIR%\package.json" (
    echo Error: website\package.json was not found.
    pause
    exit /b 1
)

echo Starting SmartDry backend...
start "SmartDry Backend" cmd /k ^
    "cd /d "%PROJECT_DIR%" && "%PYTHON_EXE%" -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000"

echo Starting SmartDry website...
start "SmartDry Website" cmd /k ^
    "cd /d "%WEBSITE_DIR%" && npm.cmd run dev -- --port 3000"

echo.
echo Backend: http://localhost:8000/docs
echo Website: http://localhost:3000
echo.
echo Both services were started in separate windows.

endlocal