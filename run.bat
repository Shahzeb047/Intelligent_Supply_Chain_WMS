@echo off
title Intelligent Supply Chain and Warehouse Management System
cd /d "%~dp0"
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate
echo Installing requirements...
pip install -r requirements.txt -q
echo.
echo Starting server - open http://127.0.0.1:5000  (admin / admin123)
start "" http://127.0.0.1:5000
python app.py
pause
