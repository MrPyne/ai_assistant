@echo off
REM Stop and remove containers, volumes, and orphans
SETLOCAL
docker-compose down --volumes --remove-orphans
ENDLOCAL
