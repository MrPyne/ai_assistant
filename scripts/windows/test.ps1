# Create venv, install requirements, run backend pytest
Param(
    [string]$BackendPath = "backend"
)

$venvPath = Join-Path $BackendPath ".venv"

if (-Not (Test-Path $venvPath)) {
    python -m venv $venvPath
}

$activate = Join-Path $venvPath "Scripts/Activate.ps1"
Write-Host "Activating venv: $activate"
. $activate

Push-Location $BackendPath
pip install --upgrade pip
if (Test-Path requirements.txt) {
    pip install -r requirements.txt
}
pytest -q
Pop-Location
