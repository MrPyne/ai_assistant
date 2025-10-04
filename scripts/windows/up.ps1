# Start development stack via docker-compose
Param(
    [switch]$Detach
)

if ($Detach) {
    docker-compose up -d --remove-orphans
} else {
    docker-compose up --remove-orphans
}
