"""FastAPI application for Word2LaTeX clipboard converter."""

import asyncio
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from queue import Empty, Queue
from threading import Thread

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from clipboard import read_clipboard_debug
from converter import convert_clipboard, convert_html
from to_clipboard import convert_to_clipboard
from history import init_db

app = FastAPI(title="Word2LaTeX", version="1.0.0")
init_db()

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


@app.post("/api/ocr")
async def ocr_image(
    image: UploadFile = File(...),
    backend: str = Form("gemini"),
    format: str = Form("markdown"),
    stream: str = Form("false"),
):
    """OCR an uploaded image using Gemini API or GOT-OCR 2.0.
    When stream=true, returns Server-Sent Events with progress logs."""
    if format not in ("latex", "markdown", "text"):
        return JSONResponse(status_code=400, content={"error": f"Invalid format: {format!r}"})
    if backend not in ("gemini", "got", "texify"):
        return JSONResponse(status_code=400, content={"error": f"Invalid backend: {backend!r}"})

    use_stream = stream.lower() in ("true", "1", "yes")
    image_bytes = await image.read()
    mime_type = image.content_type or "image/png"

    if not use_stream:
        try:
            from ocr_service import run_ocr
            result = run_ocr(image_bytes, mime_type, backend, format)
            return {"result": result, "backend": backend}
        except Exception as e:
            import traceback
            detail = traceback.format_exc()
            print(detail)
            return JSONResponse(status_code=500, content={"error": str(e), "detail": detail})

    # Streaming mode: run OCR in thread, stream logs via SSE
    queue: Queue = Queue()

    def log_cb(entry: dict) -> None:
        queue.put(("log", entry))

    def run_ocr_thread() -> None:
        try:
            log_cb({"step": "start", "msg": f"Request received ({len(image_bytes)} bytes), starting {backend}...", "elapsed_ms": 0})
            from ocr_service import run_ocr
            result = run_ocr(image_bytes, mime_type, backend, format, on_log=log_cb)
            queue.put(("result", {"result": result, "backend": backend}))
        except Exception as e:
            import traceback
            queue.put(("error", {"error": str(e), "detail": traceback.format_exc()}))
        finally:
            queue.put((None, None))

    thread = Thread(target=run_ocr_thread)
    thread.start()

    def get_from_queue():
        try:
            return queue.get(timeout=0.2)
        except Empty:
            return ("_timeout", None)

    async def event_generator():
        loop = asyncio.get_event_loop()
        while True:
            kind, data = await loop.run_in_executor(None, get_from_queue)
            if kind == "_timeout":
                continue
            if kind is None:
                break
            if kind == "log":
                yield f"event: log\ndata: {json.dumps(data)}\n\n"
            elif kind == "result":
                yield f"event: result\ndata: {json.dumps(data)}\n\n"
                break
            elif kind == "error":
                yield f"event: error\ndata: {json.dumps(data)}\n\n"
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/translate")
def translate(body: dict):
    """Translate OCR'd text to a target language via Gemini, preserving math/formatting."""
    text = body.get("text", "").strip()
    target_language = body.get("target_language", "English")
    fmt = body.get("format", "markdown")
    if not text:
        return JSONResponse(status_code=400, content={"error": "No text provided"})
    try:
        from ocr_service import translate_text
        result = translate_text(text, target_language, fmt)
        return {"result": result}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/export/docx")
def export_docx(body: dict):
    """Convert Markdown or LaTeX to a .docx file via Pandoc and return it for download."""
    text = body.get("text", "").strip()
    fmt = body.get("format", "markdown")
    if not text:
        return JSONResponse(status_code=400, content={"error": "No text provided"})
    if fmt not in ("markdown", "latex"):
        return JSONResponse(status_code=400, content={"error": f"Invalid format: {fmt!r}"})
    if not shutil.which("pandoc"):
        return JSONResponse(status_code=500, content={"error": "Pandoc is not installed"})

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        result = subprocess.run(
            ["pandoc", "-f", fmt, "-t", "docx", "-o", str(tmp_path)],
            input=text,
            text=True,
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            return JSONResponse(status_code=500, content={"error": result.stderr or "Pandoc failed"})
        docx_bytes = tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="output.docx"'},
    )


@app.get("/api/history/{tab}")
def get_history(tab: str, limit: int = 50):
    from history import get_entries
    return {"items": get_entries(tab, limit)}


@app.post("/api/history")
def add_history(body: dict):
    tab       = body.get("tab", "").strip()
    title     = body.get("title", "Untitled")
    data      = body.get("data", {})
    thumbnail = body.get("thumbnail")
    image     = body.get("image")
    if not tab:
        return JSONResponse(status_code=400, content={"error": "tab required"})
    from history import add_entry
    entry_id = add_entry(tab, title, data, thumbnail, image)
    return {"id": entry_id}


@app.delete("/api/history/item/{entry_id}")
def delete_history_item(entry_id: int):
    from history import delete_entry
    return {"deleted": delete_entry(entry_id)}


@app.delete("/api/history/tab/{tab}")
def clear_history(tab: str):
    from history import clear_tab
    return {"cleared": clear_tab(tab)}


# Serve frontend static files in production
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
