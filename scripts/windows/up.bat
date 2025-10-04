@echo off
REM Start the development stack using docker-compose
SETLOCAL
IF "%~1"=="" (
  docker-compose up --build
) ELSE (
  docker-compose up --build %*
)
ENDLOCAL
