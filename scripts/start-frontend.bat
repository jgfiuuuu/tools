@echo off
setlocal

set "REPO_ROOT=%~dp0.."
set "FRONTEND_DIR=%REPO_ROOT%\frontend"

if not exist "%FRONTEND_DIR%\node_modules" (
  echo Frontend dependencies not found.
  echo Run: cd /d "%FRONTEND_DIR%" ^&^& npm.cmd install
  pause
  exit /b 1
)

if "%~1"=="--check" (
  echo Frontend startup check passed.
  exit /b 0
)

cd /d "%FRONTEND_DIR%"

echo Starting frontend: http://localhost:5174
npm.cmd run dev -- --host 127.0.0.1 --port 5174
