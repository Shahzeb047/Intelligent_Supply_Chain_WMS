#!/usr/bin/env bash
cd "$(dirname "$0")"
[ -d venv ] || python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -q
echo "Open http://127.0.0.1:5000  (admin / admin123)"
python app.py
