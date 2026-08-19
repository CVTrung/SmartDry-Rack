@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "TEST_PYTHON=%PROJECT_DIR%.venv\Scripts\python.exe"

echo ========================================
echo SmartDry test runner
echo ========================================
echo.

if not exist "%TEST_PYTHON%" (
    echo ERROR: Virtual environment Python was not found:
    echo %TEST_PYTHON%
    pause
    exit /b 1
)

pushd "%PROJECT_DIR%"
set PYTHONPATH=%CD%
set RUN_OPENWEATHER_INTEGRATION_TESTS=1
set ALLOW_FIREBASE_SAMPLE_WRITE=1
set RUN_FIRESTORE_INTEGRATION_TESTS=1
set RUN_FIREBASE_INTEGRATION_TESTS=1

echo Running tests...
echo.
"%TEST_PYTHON%" -m unittest discover -s tests -p "test*.py" -v

if errorlevel 1 (
    echo.
    echo ========================================
    echo One or more tests FAILED.
    echo Review the errors above.
    echo ========================================
    popd
    pause
    exit /b 1
)

echo.
echo ========================================
echo All tests PASSED.
echo ========================================
popd
pause
exit /b 0
