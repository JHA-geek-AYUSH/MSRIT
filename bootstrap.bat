@echo off
echo ════════════════════════════════════════════════
echo   GemmaFinOS — One-Click Bootstrap
echo ════════════════════════════════════════════════
echo.

cd /d "%~dp0"

echo [1/5] Killing old server on port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo   OK

echo [2/5] Training XGBoost model...
cd backend
.\venv\Scripts\Activate.ps1
python -m app.ml.generate_dataset
if %ERRORLEVEL% NEQ 0 (
    echo   WARNING: Model training failed — continuing with fallback
)
echo   OK

echo [3/5] Seeding demo data into NeonDB...
python seed_demo_data.py
if %ERRORLEVEL% NEQ 0 (
    echo   WARNING: Seed failed — continuing
)
echo   OK

echo [4/5] Starting backend server...
start "GemmaFinOS Backend" cmd /c "python run.py"
echo   Backend starting on http://localhost:8000

echo [5/5] Starting frontend...
cd ..\frontend
start "GemmaFinOS Frontend" cmd /c "npm run dev"
echo   Frontend starting on http://localhost:3000

echo.
echo ════════════════════════════════════════════════
echo   All services starting!
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:3000
echo   API Docs: http://localhost:8000/docs
echo ════════════════════════════════════════════════

pause
