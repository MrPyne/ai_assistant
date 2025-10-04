@echo off
REM Start development stack
docker-compose up --build
exit /b %ERRORLEVEL%