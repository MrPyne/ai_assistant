# Run backend tests inside a Python virtualenv
$venvPath = "backend\.venv"
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error "Python not found in PATH. Install Python 3.9+ or use WSL."
    exit 1
}

if (-not (Test-Path $venvPath)) {
    Write-Host "Creating virtualenv at $venvPath"
    python -m venv $venvPath
}

$activate = Join-Path $venvPath "Scripts\Activate.ps1"
Write-Host "Activating virtualenv: $activate"
& $activate

Write-Host "Installing requirements"
pip install -r backend/requirements.txt

Write-Host "Running pytest"
pytest -q backend
