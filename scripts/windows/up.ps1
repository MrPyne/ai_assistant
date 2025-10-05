# Start the stack (detached). Uses docker-compose if available, otherwise docker compose
$composeCmd = ""
if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
    $composeCmd = "docker-compose"
} else {
    $composeCmd = "docker compose"
}

Write-Host "Running: $composeCmd up --build -d"
& $composeCmd up --build -d
