@echo off
REM Release helper: build images and optionally tag/push. Usage: release.bat VERSION=0.1.0 REGISTRY=your.registry.com/yourrepo
SETLOCAL
if "%~1"=="" (
  echo Usage: %~nx0 VERSION=<version> [REGISTRY=<registry>]
  exit /b 1
)
for %%I in (%*) do set "%%I"
if not defined VERSION (
  echo VERSION is required (e.g. release.bat VERSION=0.1.0)
  exit /b 1
)

echo Building images...
docker-compose build --no-cache
echo Tagging images...
set IMAGE_BACKEND_TAG=%REGISTRY%/no_code_ai_assistant-backend:%VERSION%
if not defined REGISTRY (
  echo REGISTRY not set; defaulting to local tags
) else (
  docker tag no_code_ai_assistant-backend:latest %IMAGE_BACKEND_TAG% || echo tagging failed
  echo Push images if REGISTRY provided...
  docker push %IMAGE_BACKEND_TAG%
)
echo Release complete.
exit /b %ERRORLEVEL%