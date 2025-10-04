@echo off
REM Stop and remove containers and volumes
docker-compose down --volumes --remove-orphans
exit /b %ERRORLEVEL%