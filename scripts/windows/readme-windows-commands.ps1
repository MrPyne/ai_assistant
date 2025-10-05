<# Helper: Prints common Windows commands for working with the project. #>
Write-Host "Windows Development Quick Commands"
Write-Host "---------------------------------"
Write-Host "Build images:"; Write-Host "  ./scripts/windows/build.ps1"
Write-Host "Start stack:"; Write-Host "  ./scripts/windows/up.ps1"
Write-Host "Stop stack:"; Write-Host "  ./scripts/windows/down.ps1"
Write-Host "Run backend tests:"; Write-Host "  ./scripts/windows/test.ps1"
Write-Host "Bootstrap dev (create .env from .env.example and start):"; Write-Host "  ./scripts/windows/setup-dev.ps1"
