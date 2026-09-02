@echo off
setlocal

set PROJECT_DIR=C:\dangi-dongi
set API_SERVICE=DangiDongi-API
set BOT_SERVICE=DangiDongi-Bot
set PYTHON=%PROJECT_DIR%\.venv\Scripts\python.exe
set PIP=%PROJECT_DIR%\.venv\Scripts\pip.exe
set ALEMBIC=%PROJECT_DIR%\.venv\Scripts\alembic.exe

cd /d %PROJECT_DIR%
if errorlevel 1 goto :fail

echo [1/6] Stopping services...
net stop %BOT_SERVICE% >nul 2>&1
net stop %API_SERVICE% >nul 2>&1

echo [2/6] Pulling release/v1.0.0 from GitHub...
git fetch origin
if errorlevel 1 goto :fail
git checkout release/v1.0.0
if errorlevel 1 goto :fail
git pull --ff-only origin release/v1.0.0
if errorlevel 1 goto :fail

echo [3/6] Updating dependencies...
"%PYTHON%" -m pip install --upgrade pip
if errorlevel 1 goto :fail
"%PIP%" install -r requirements.txt
if errorlevel 1 goto :fail

echo [4/6] Applying database migrations...
"%ALEMBIC%" upgrade head
if errorlevel 1 goto :fail

echo [5/6] Starting API...
net start %API_SERVICE%
if errorlevel 1 goto :fail
timeout /t 3 /nobreak >nul

echo [6/6] Starting Bot...
net start %BOT_SERVICE%
if errorlevel 1 goto :fail

echo.
echo Deployment completed successfully.
sc query %API_SERVICE% | find "STATE"
sc query %BOT_SERVICE% | find "STATE"
exit /b 0

:fail
echo.
echo Deployment failed. Check the command output and logs in C:\dangi-dongi\logs.
echo Attempting to start services again...
net start %API_SERVICE% >nul 2>&1
timeout /t 2 /nobreak >nul
net start %BOT_SERVICE% >nul 2>&1
exit /b 1
