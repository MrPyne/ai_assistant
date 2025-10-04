# Install frontend deps and build
Param(
    [string]$FrontendPath = "frontend"
)

Push-Location $FrontendPath
if (Test-Path package-lock.json -or Test-Path yarn.lock) {
    npm ci
} else {
    npm install
}
npm run build
Pop-Location
