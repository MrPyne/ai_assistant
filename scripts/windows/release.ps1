<#
Release helper: build and optionally tag/push images.
Usage:
  ./release.ps1 -Version 0.1.0 -Registry your.registry.com/yourrepo
#>
Param(
    [Parameter(Mandatory=$true)][string]$Version,
    [string]$Registry
)

Write-Host "Building images..."
docker-compose build --no-cache

if ($Registry) {
    $imageTag = "${Registry}/no_code_ai_assistant-backend:$Version"
    docker tag no_code_ai_assistant-backend:latest $imageTag
    Write-Host "Pushing $imageTag..."
    docker push $imageTag
} else {
    Write-Host "No registry provided; images built locally with :latest tag"
}

Write-Host "Release complete."
