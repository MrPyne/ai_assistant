# Bootstrap development environment on Windows
# Copies .env.example -> .env if not present, and then starts the stack
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$envExample = Join-Path $repoRoot ".env.example"
$envFile = Join-Path $repoRoot ".env"

if (-not (Test-Path $envExample)) {
    Write-Error ".env.example not found in repo root"
    exit 1
}

if (-not (Test-Path $envFile)) {
    Write-Host "Creating .env from .env.example"
    Copy-Item $envExample $envFile
} else {
    Write-Host ".env already exists, leaving it alone"
}

# Start docker-compose stack
$composeCmd = ""
if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
    $composeCmd = "docker-compose"
} else {
    $composeCmd = "docker compose"
}

Write-Host "Starting stack: $composeCmd up --build -d"
& $composeCmd up --build -d
