#!/bin/bash
set -e

echo "Starting Word2LaTeX..."
echo

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Start backend
echo "[Backend] Starting FastAPI server on port 8741..."
(cd "$SCRIPT_DIR/backend" && pip install -r requirements.txt -q && uvicorn main:app --reload --port 8741) &
BACKEND_PID=$!

# Wait for backend to start
sleep 3

# Start frontend
echo "[Frontend] Starting Vite dev server on port 5173..."
(cd "$SCRIPT_DIR/frontend" && npm install && npm run dev) &
FRONTEND_PID=$!

echo
echo "Word2LaTeX is running!"
echo "  Backend:  http://localhost:8741"
echo "  Frontend: http://localhost:5173"
echo
echo "Press Ctrl+C to stop both servers..."

cleanup() {
    echo "Stopping servers..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    exit 0
}

trap cleanup INT TERM
wait
