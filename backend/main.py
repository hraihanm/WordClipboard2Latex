"""FastAPI application for Word2LaTeX clipboard converter."""

import shutil
import subprocess
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from clipboard import read_clipboard_debug
from converter import convert_clipboard, convert_html
from to_clipboard import convert_to_clipboard

app = FastAPI(title="Word2LaTeX", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    """Health check — also reports Pandoc availability."""
    pandoc_path = shutil.which("pandoc")
    pandoc_version = None
    if pandoc_path:
        try:
            result = subprocess.run(
                ["pandoc", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            first_line = result.stdout.splitlines()[0] if result.stdout else ""
            pandoc_version = first_line
        except Exception:
            pass
    return {
        "status": "ok",
        "pandoc_installed": pandoc_path is not None,
        "pandoc_version": pandoc_version,
    }


@app.get("/api/clipboard-info")
def clipboard_info():
    """Return debug info about clipboard contents: available formats and raw HTML."""
    try:
        return read_clipboard_debug()
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)},
        )


@app.get("/api/convert")
def convert():
    """Read the Windows clipboard and convert to LaTeX/Markdown/HTML."""
    try:
        result = convert_clipboard()
        return result
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "warnings": [str(e)]},
        )


@app.post("/api/to-clipboard")
def to_clipboard(body: dict):
    """Convert Markdown or LaTeX text and write it to the Windows clipboard.

    Body: ``{"text": "...", "format": "markdown" | "latex"}``
    """
    text = body.get("text", "").strip()
    fmt = body.get("format", "markdown")
    if not text:
        return JSONResponse(
            status_code=400,
            content={"error": "No text provided", "warnings": ["No text provided"]},
        )
    try:
        result = convert_to_clipboard(text, fmt)
        return result
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/convert/text")
def convert_text(body: dict):
    """Accept raw HTML+OMML and convert (useful for testing without clipboard)."""
    html = body.get("html", "")
    if not html:
        return JSONResponse(
            status_code=400,
            content={"error": "No HTML provided", "warnings": ["No HTML provided"]},
        )
    try:
        result = convert_html(html)
        return result
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "warnings": [str(e)]},
        )


# Serve frontend static files in production
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
