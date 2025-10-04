@echo off
REM Build backend Docker image
docker build -t no_code_ai_assistant-backend -f backend/Dockerfile backend
exit /b %ERRORLEVEL%