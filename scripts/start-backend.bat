@echo off
setlocal

set "REPO_ROOT=%~dp0.."
set "BACKEND_DIR=%REPO_ROOT%\backend"
set "PYTHON_EXE=%BACKEND_DIR%\.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
  echo Backend virtual environment not found.
  echo Run: cd /d "%BACKEND_DIR%" ^&^& uv sync
  pause
  exit /b 1
)

if "%~1"=="--check" (
  echo Backend startup check passed.
  exit /b 0
)

cd /d "%BACKEND_DIR%"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo Starting backend: http://localhost:8000
"%PYTHON_EXE%" -m uvicorn main:app --app-dir src --host 0.0.0.0 --port 8000 --reload
