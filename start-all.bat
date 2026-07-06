@echo off
setlocal

set "REPO_ROOT=%~dp0"

echo Starting CiteWeave...
echo Backend:  http://localhost:8000
echo Frontend: http://localhost:5174
echo.

start "CiteWeave Backend" cmd /k call "%REPO_ROOT%scripts\start-backend.bat"
start "CiteWeave Frontend" cmd /k call "%REPO_ROOT%scripts\start-frontend.bat"

echo Started backend and frontend in separate command windows.
echo Close those windows to stop the services.
pause
