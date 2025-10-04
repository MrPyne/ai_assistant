@echo off
REM Build docker images
docker-compose build
exit /b %ERRORLEVEL%