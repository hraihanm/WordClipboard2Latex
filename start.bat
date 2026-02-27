@echo off
setlocal EnableDelayedExpansion
echo Starting Word2LaTeX...
echo.

:: ---------------------------------------------------------------------------
:: Environment: add Pandoc to PATH (edit PANDOC_PATH if installed elsewhere)
:: ---------------------------------------------------------------------------
set "PANDOC_PATH=C:\Program Files\Pandoc"
if exist "%PANDOC_PATH%\pandoc.exe" (
    set "PATH=%PATH%;%PANDOC_PATH%"
    echo [Setup] Pandoc found at %PANDOC_PATH%
) else (
    echo [Setup] Pandoc not found at %PANDOC_PATH% - equation conversion will be limited.
    echo          Install from https://pandoc.org/installing.html
)
echo.

:: ---------------------------------------------------------------------------
:: Python venv
:: ---------------------------------------------------------------------------
set "BACKEND_DIR=%~dp0backend"
set "VENV_DIR=%BACKEND_DIR%\venv"

if not exist "%VENV_DIR%" (
    echo [Setup] Creating Python virtual environment...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [Error] Failed to create venv. Ensure Python 3.10+ is installed.
        pause
        exit /b 1
    )
)

:: Upgrade pip and install requirements in venv
echo [Setup] Installing Python dependencies...
"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip
"%VENV_DIR%\Scripts\pip.exe" install -r "%BACKEND_DIR%\requirements.txt"
if errorlevel 1 (
    echo [Error] Failed to install requirements.
    pause
    exit /b 1
)
echo.

:: ---------------------------------------------------------------------------
:: Start backend (inherits PATH with Pandoc from above)
:: ---------------------------------------------------------------------------
echo [Backend] Starting FastAPI server on port 8741...
start "Word2LaTeX Backend" cmd /c "cd /d "%BACKEND_DIR%" && "%VENV_DIR%\Scripts\activate.bat" && uvicorn main:app --reload --port 8741"

:: Wait for backend to start
timeout /t 3 /nobreak >nul

:: ---------------------------------------------------------------------------
:: Start frontend
:: ---------------------------------------------------------------------------
echo [Frontend] Starting Vite dev server on port 5173...
start "Word2LaTeX Frontend" cmd /c "cd /d "%~dp0frontend" && npm install && npm run dev"

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
