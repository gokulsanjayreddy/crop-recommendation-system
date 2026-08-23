@echo off
REM One-click launcher: starts API + UI at http://127.0.0.1:8000
cd /d "%~dp0"
echo Starting AI Crop Recommendation System...
echo Browser will open at http://127.0.0.1:8000 (first load takes ~10s while models warm up)
start "" http://127.0.0.1:8000
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
