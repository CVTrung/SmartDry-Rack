@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "TEST_PYTHON=%PROJECT_DIR%.venv\Scripts\python.exe"
set "WEBSITE_DIR=%PROJECT_DIR%website"
set "TEST_FAILED=0"

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

echo [1/3] Checking Python syntax...
"%TEST_PYTHON%" -m compileall -q "%PROJECT_DIR%backend" "%PROJECT_DIR%tests"

if errorlevel 1 (
    echo FAILED: Python syntax check
    set "TEST_FAILED=1"
) else (
    echo PASSED: Python syntax check
)

echo.
echo [2/3] Running backend tests...
pushd "%PROJECT_DIR%"
"%TEST_PYTHON%" -m unittest discover -s tests -p "test_*.py"
if errorlevel 1 (
    echo FAILED: Backend tests
    set "TEST_FAILED=1"
) else (
    echo PASSED: Backend tests
)
popd

echo.
echo [3/3] Building website...
pushd "%WEBSITE_DIR%"
call npm.cmd run build
if errorlevel 1 (
    echo FAILED: Website build
    set "TEST_FAILED=1"
) else (
    echo PASSED: Website build
)
popd

echo.
echo ========================================

if "%TEST_FAILED%"=="1" (
    echo One or more checks FAILED.
    echo Review the errors above.
    echo ========================================
    pause
    exit /b 1
)

echo All available checks PASSED.
echo ========================================
pause
exit /b 0