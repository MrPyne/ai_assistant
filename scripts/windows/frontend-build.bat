@echo off
REM Build frontend production bundle
cd frontend
npm ci || npm install --no-audit --no-fund
npm run build
exit /b %ERRORLEVEL%