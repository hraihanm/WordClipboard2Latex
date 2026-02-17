@echo off
echo Starting Word2LaTeX...
echo.

:: Start backend
echo [Backend] Starting FastAPI server on port 8741...
start "Word2LaTeX Backend" cmd /c "cd /d %~dp0backend && pip install -r requirements.txt -q && uvicorn main:app --reload --port 8741"

:: Wait a moment for backend to start
timeout /t 3 /nobreak >nul

:: Start frontend
echo [Frontend] Starting Vite dev server on port 5173...
start "Word2LaTeX Frontend" cmd /c "cd /d %~dp0frontend && npm install && npm run dev"

echo.
echo Word2LaTeX is starting up!
echo   Backend:  http://localhost:8741
echo   Frontend: http://localhost:5173
echo.
echo Press any key to stop both servers...
pause >nul

:: Kill the servers
taskkill /fi "WINDOWTITLE eq Word2LaTeX Backend" >nul 2>&1
taskkill /fi "WINDOWTITLE eq Word2LaTeX Frontend" >nul 2>&1
