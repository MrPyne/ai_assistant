# Build docker images (backend/frontend) for development
Param(
    [switch]$NoCache
)

if ($NoCache) {
    docker-compose build --no-cache
} else {
    docker-compose build
}
