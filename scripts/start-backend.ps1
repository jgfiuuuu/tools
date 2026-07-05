$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$python = Join-Path $backendDir ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Error "Backend virtual environment not found. Run: cd backend; uv sync"
}

Set-Location $backendDir
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

& $python -m uvicorn main:app --app-dir src --host 0.0.0.0 --port 8000 --reload
