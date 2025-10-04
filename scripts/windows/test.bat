@echo off
REM Run backend tests in a virtualenv (Windows)
SETLOCAL
if not exist backend\.venv (
    python -m venv backend\.venv
)
call backend\.venv\Scripts\activate
pip install -r backend\requirements.txt
cd backend
pytest -q
exit /b %ERRORLEVEL%