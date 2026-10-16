@echo off
setlocal

set "PROJECT_DIR=%~dp0BCM Troubleshooting Web"
set "APP_DIR=%PROJECT_DIR%\troubleshoot-main\troubleshoot-main"
set "REQUIREMENTS=%PROJECT_DIR%\troubleshoot-main\requirements.txt"
set "PYTHON=%PROJECT_DIR%\.venv\Scripts\python.exe"

if not exist "%REQUIREMENTS%" (
    echo ERROR: Could not find the requirements file:
    echo "%REQUIREMENTS%"
    exit /b 1
)

if not exist "%APP_DIR%\manage.py" (
    echo ERROR: Could not find the Django application:
    echo "%APP_DIR%\manage.py"
    exit /b 1
)

if not exist "%PYTHON%" (
    echo Creating a virtual environment...
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3 -m venv "%PROJECT_DIR%\.venv"
        if errorlevel 1 goto setup_failed
        goto install_requirements
    )

    where python >nul 2>&1
    if errorlevel 1 goto python_missing
    python -m venv "%PROJECT_DIR%\.venv"
    if errorlevel 1 goto setup_failed
)

:install_requirements
echo Installing project requirements...
"%PYTHON%" -m pip install -r "%REQUIREMENTS%"
if errorlevel 1 goto requirements_failed

pushd "%APP_DIR%"
if errorlevel 1 goto app_directory_failed

echo Applying database migrations...
"%PYTHON%" manage.py migrate
if errorlevel 1 goto migration_failed

echo Starting the website at http://127.0.0.1:8000/
echo Keep this window open while using the website. Press Ctrl+C to stop it.
"%PYTHON%" manage.py runserver 127.0.0.1:8000
set "SERVER_EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %SERVER_EXIT_CODE%

:python_missing
echo ERROR: Python 3 is required but was not found.
echo Install Python 3.12 or newer, then run this file again.
exit /b 1

:setup_failed
echo ERROR: Could not create the Python virtual environment.
exit /b 1

:requirements_failed
echo ERROR: Dependency installation failed. Check your internet connection and try again.
exit /b 1

:app_directory_failed
echo ERROR: Could not enter the Django application directory.
exit /b 1

:migration_failed
popd
echo ERROR: Database migrations failed; the website was not started.
exit /b 1
