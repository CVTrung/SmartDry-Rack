@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "PYTHON_EXE=%PROJECT_DIR%.venv\Scripts\python.exe"
set "ENV_FILE=%PROJECT_DIR%.env"

echo ========================================
echo SmartDry weather notification test
echo ========================================
echo.

if not exist "%PYTHON_EXE%" (
    echo ERROR: Python virtual environment was not found:
    echo %PYTHON_EXE%
    echo.
    echo Create it and install requirements before running this file.
    pause
    exit /b 1
)

if not exist "%ENV_FILE%" (
    echo ERROR: Backend environment file was not found:
    echo %ENV_FILE%
    echo.
    echo Copy .env.example to .env and configure Firebase, OpenWeather,
    echo the device and location, and Gmail if email delivery is enabled.
    pause
    exit /b 1
)

pushd "%PROJECT_DIR%"
set "PYTHONPATH=%PROJECT_DIR%"

rem Shell variables override the scheduling values in .env for this run only.
set "CURRENT_WEATHER_CHECK_INTERVAL_MINUTES=1"
set "FORECAST_CHECK_INTERVAL_MINUTES=1"

echo Running the initial current-weather and forecast checks...
echo Further checks will run every 1 minute.
echo Every enabled Firebase account will be checked.
echo Notifications are created only when the configured rain rules match.
echo Press Ctrl+C to stop the backend.
echo.
echo API documentation: http://127.0.0.1:8000/docs
echo.

rem Do not use --reload here: one process should own the test scheduler.
"%PYTHON_EXE%" -m uvicorn backend.main:app ^
    --host 127.0.0.1 ^
    --port 8000 ^
    --log-level info

set "BACKEND_EXIT_CODE=%ERRORLEVEL%"
popd

if not "%BACKEND_EXIT_CODE%"=="0" (
    echo.
    echo Backend stopped with exit code %BACKEND_EXIT_CODE%.
    echo Review the messages above for configuration or delivery errors.
    pause
)

exit /b %BACKEND_EXIT_CODE%
