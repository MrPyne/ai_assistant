@echo off
REM Create a virtualenv and run backend tests
SETLOCAL
python -m venv backend\.venv
call backend\.venv\Scripts\activate.bat
pip install -r backend\requirements.txt
pushd backend
pytest -q
popd
ENDLOCAL
