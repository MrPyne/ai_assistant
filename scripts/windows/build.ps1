# Build backend and frontend images and install frontend deps if not already
$composeCmd = ""
if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
    $composeCmd = "docker-compose"
} else {
    $composeCmd = "docker compose"
}

# Optionally install frontend deps locally to enable local builds outside Docker
if (Test-Path "frontend/package.json") {
    Write-Host "Installing frontend dependencies (npm ci)..."
    Push-Location frontend
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        npm ci
    } else {
        Write-Host "npm not found in PATH. Skipping local install. Docker will handle frontend build."
    }
    Pop-Location
}

Write-Host "Building images with $composeCmd build"
& $composeCmd build
