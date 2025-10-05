# Stop the stack and remove volumes/orphans
$composeCmd = ""
if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
    $composeCmd = "docker-compose"
} else {
    $composeCmd = "docker compose"
}

Write-Host "Running: $composeCmd down --volumes --remove-orphans"
& $composeCmd down --volumes --remove-orphans
