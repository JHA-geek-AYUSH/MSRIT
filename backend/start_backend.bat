@echo off
cd /d d:\gemmaFin_os\backend
echo Starting GemmaFinOS Minimal Backend...
echo.
echo http://localhost:8000
echo http://localhost:8000/docs
echo.
python -m uvicorn app_minimal:app --host 0.0.0.0 --port 8000
pause
