"""OCR service — Gemini API, Ollama, GOT-OCR 2.0, and texify backends."""

from __future__ import annotations

import base64
import json
import os
import tempfile
import time
import urllib.request
import urllib.error
import warnings
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv
load_dotenv()

# Suppress noisy but harmless warnings from GOT-OCR's internal code
warnings.filterwarnings("ignore", category=SyntaxWarning)
warnings.filterwarnings("ignore", message=".*attention mask.*", category=UserWarning)
warnings.filterwarnings("ignore", message=".*pad_token_id.*", category=UserWarning)

# Override via GEMINI_MODEL env var if needed (e.g. "gemini-2.5-flash")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

PROMPTS: dict[str, str] = {
    "latex": (
        "Convert the content of this image to LaTeX. "
        "Use $$...$$ for display equations and $...$ for inline math. "
        "For tables use LaTeX tabular environments. "
        "Output only the LaTeX source, no explanation."
    ),
    "markdown": (
        "Convert the content of this image to Markdown. "
        "Use $...$ for inline math and $$...$$ for display math (KaTeX/MathJax style). "
        "For tables use GFM pipe tables. "
        "Preserve headings and paragraph structure. "
        "Output only the Markdown, no explanation."
    ),
    "text": (
        "Transcribe all text in this image accurately. "
        "Preserve structure (headings, lists, paragraphs). "
        "Write mathematical expressions in readable plain-text form. "
        "Output only the transcription, no explanation."
    ),
}


# ---------------------------------------------------------------------------
# Gemini backend
# ---------------------------------------------------------------------------

def ocr_gemini(image_bytes: bytes, mime_type: str, fmt: str, on_log: Callable[[dict], None] | None = None) -> str:
    from google.genai import types

    t0 = time.perf_counter()
    if on_log:
        on_log({"step": "gemini_init", "msg": "Initializing Gemini client...", "elapsed_ms": 0})

    client = _make_gemini_client()
    if on_log:
        on_log({"step": "gemini_ready", "msg": "Client ready, calling API...", "elapsed_ms": round((time.perf_counter() - t0) * 1000)})

    t_api = time.perf_counter()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            PROMPTS[fmt],
        ],
    )
    if on_log:
        on_log({"step": "gemini_done", "msg": f"Gemini API completed ({len(response.text)} chars)", "elapsed_ms": round((time.perf_counter() - t_api) * 1000)})
    return response.text


# ---------------------------------------------------------------------------
# Ollama backend (local or remote API)
# ---------------------------------------------------------------------------

def ocr_ollama(image_bytes: bytes, mime_type: str, fmt: str, on_log: Callable[[dict], None] | None = None) -> str:
    """OCR via Ollama vision API. Uses base_url and model from settings."""
    from settings import get_all
    settings = get_all()
    base_url = (settings.get("ollama_base_url") or "http://localhost:11434").rstrip("/")
    model = settings.get("ollama_model") or "llava"

    t0 = time.perf_counter()
    if on_log:
        on_log({"step": "ollama_init", "msg": f"Connecting to {base_url} ({model})...", "elapsed_ms": 0})

    img_b64 = base64.b64encode(image_bytes).decode("ascii")
    prompt = PROMPTS[fmt]

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt, "images": [img_b64]},
        ],
        "stream": False,
    }

    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Ollama connection failed: {e.reason}. "
            f"Ensure Ollama is running at {base_url} and model '{model}' is pulled (ollama pull {model})."
        ) from e
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"Ollama API error {e.code}: {body}") from e

    if on_log:
        on_log({"step": "ollama_done", "msg": "Ollama API completed", "elapsed_ms": round((time.perf_counter() - t0) * 1000)})

    msg = data.get("message", {})
    content = msg.get("content", "")
    if not content:
        raise RuntimeError("Ollama returned empty response")
    return content.strip()


# ---------------------------------------------------------------------------
# GOT-OCR 2.0 backend (local, lazy-loaded)
# ---------------------------------------------------------------------------

_got_model = None
_got_tokenizer = None


def _patch_dynamic_cache() -> None:
    """GOT-OCR 2.0 uses DynamicCache.seen_tokens which was renamed in transformers >= 4.40."""
    try:
        from transformers.cache_utils import DynamicCache
        original_init = DynamicCache.__init__

        def patched_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            # Add seen_tokens attribute that GOT-OCR expects
            if not hasattr(self, 'seen_tokens'):
                self.seen_tokens = 0

        DynamicCache.__init__ = patched_init
    except Exception:
        pass


def _load_got():
    global _got_model, _got_tokenizer
    if _got_model is not None:
        return _got_model, _got_tokenizer

    _patch_dynamic_cache()

    try:
        from transformers import AutoModel, AutoTokenizer
        import torch
    except ImportError:
        raise RuntimeError(
            "GOT-OCR 2.0 requires extra packages. Install with:\n"
            "  pip install transformers torch tiktoken accelerate pillow\n"
            "Or use the Gemini backend (set GEMINI_API_KEY in .env)."
        )

    # Check CUDA availability and set device
    device_map = "cuda" if torch.cuda.is_available() else "cpu"
    if device_map == "cuda":
        print(f"CUDA available ({torch.cuda.device_count()} device(s)), using GPU for GOT-OCR")
    else:
        print("CUDA not available, using CPU for GOT-OCR. This may be slower.")

    model_id = "ucaslcl/GOT-OCR2_0"
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    model = AutoModel.from_pretrained(
        model_id,
        trust_remote_code=True,
        low_cpu_mem_usage=True,
        device_map=device_map,
        use_safetensors=True,
        pad_token_id=tokenizer.eos_token_id,
    ).eval()

    _got_model = model
    _got_tokenizer = tokenizer
    return model, tokenizer


def ocr_got(image_bytes: bytes, fmt: str, on_log: Callable[[dict], None] | None = None) -> str:
    import traceback
    ocr_type = "ocr" if fmt == "text" else "format"
    _patch_dynamic_cache()  # re-apply each call in case model was already cached

    if on_log:
        on_log({"step": "got_load", "msg": "Loading GOT-OCR model (first run may download ~2GB)...", "elapsed_ms": 0})
    t0 = time.perf_counter()
    model, tokenizer = _load_got()
    if on_log:
        on_log({"step": "got_loaded", "msg": "Model loaded", "elapsed_ms": round((time.perf_counter() - t0) * 1000)})

    # Write to temp file, flush and close before GOT-OCR opens it (required on Windows)
    if on_log:
        on_log({"step": "got_temp", "msg": "Writing temp file...", "elapsed_ms": round((time.perf_counter() - t0) * 1000)})
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(image_bytes)
        tmp.flush()
        tmp_path = tmp.name  # file is closed here when 'with' exits

    # Use forward slashes — some internal libs choke on Windows backslashes
    tmp_path_fwd = tmp_path.replace("\\", "/")

    try:
        if on_log:
            on_log({"step": "got_inference", "msg": "Running GOT-OCR inference...", "elapsed_ms": round((time.perf_counter() - t0) * 1000)})
        t_inf = time.perf_counter()
        result = model.chat(tokenizer, tmp_path_fwd, ocr_type=ocr_type)
        if on_log:
            on_log({"step": "got_done", "msg": f"Inference complete ({len(result)} chars)", "elapsed_ms": round((time.perf_counter() - t_inf) * 1000)})
        return result
    except Exception:
        raise RuntimeError(traceback.format_exc())
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Translation (Gemini only — always uses the same API key)
# ---------------------------------------------------------------------------

def _make_gemini_client():
    import google.genai as genai
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY environment variable is not set. "
            "Get a key at https://aistudio.google.com/apikey"
        )
    return genai.Client(api_key=api_key)


def translate_text(text: str, target_language: str, fmt: str) -> str:
    """Translate text to target_language while preserving math and formatting."""
    client = _make_gemini_client()

    prompt = (
        f"Translate the following text to {target_language}.\n"
        "Rules:\n"
        "- Preserve ALL math expressions exactly as written "
        "($...$, $$...$$, \\begin{{...}}...\\end{{...}}, \\[...\\]).\n"
        "- Preserve all Markdown/LaTeX formatting (headings, bold, italic, "
        "tables, environments) — only translate the natural-language text.\n"
        "- Do not add explanations, notes, or commentary.\n"
        "- Output only the translated content.\n\n"
        f"{text}"
    )

    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    return response.text


# ---------------------------------------------------------------------------
# texify backend (local, lazy-loaded) — equation crops → LaTeX
# ---------------------------------------------------------------------------

_texify_model = None
_texify_processor = None


def _load_texify():
    global _texify_model, _texify_processor
    if _texify_model is not None:
        return _texify_model, _texify_processor
    try:
        from texify.model.model import load_model
        from texify.model.processor import load_processor
    except ImportError:
        raise RuntimeError(
            "texify is not installed. Install with:\n  pip install texify>=0.2.1"
        )
    try:
        _texify_model = load_model()
        _texify_processor = load_processor()
    except (AttributeError, TypeError) as e:
        raise RuntimeError(
            "texify/transformers version mismatch. Try:\n"
            "  pip install texify>=0.2.1 'transformers>=4.46,<5.0'\n"
            f"Original error: {e}"
        )
    return _texify_model, _texify_processor


def ocr_texify(image_bytes: bytes, on_log: Callable[[dict], None] | None = None) -> str:
    """OCR an equation crop using texify. Always returns LaTeX."""
    import io
    from PIL import Image
    from texify.inference import batch_inference

    t0 = time.perf_counter()
    if on_log:
        on_log({"step": "texify_load", "msg": "Loading texify model (first run may download)...", "elapsed_ms": 0})
    model, processor = _load_texify()
    if on_log:
        on_log({"step": "texify_loaded", "msg": "Model loaded", "elapsed_ms": round((time.perf_counter() - t0) * 1000)})

    if on_log:
        on_log({"step": "texify_prep", "msg": "Preparing image...", "elapsed_ms": round((time.perf_counter() - t0) * 1000)})
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    if on_log:
        on_log({"step": "texify_inference", "msg": "Running texify inference...", "elapsed_ms": round((time.perf_counter() - t0) * 1000)})
    t_inf = time.perf_counter()
    results = batch_inference([img], model, processor)
    if on_log:
        on_log({"step": "texify_done", "msg": "Inference complete", "elapsed_ms": round((time.perf_counter() - t_inf) * 1000)})
    return results[0] if results else ""


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def run_ocr(image_bytes: bytes, mime_type: str, backend: str, fmt: str, on_log: Callable[[dict], None] | None = None) -> str:
    if backend == "gemini":
        return ocr_gemini(image_bytes, mime_type, fmt, on_log)
    elif backend == "ollama":
        return ocr_ollama(image_bytes, mime_type, fmt, on_log)
    elif backend == "got":
        return ocr_got(image_bytes, fmt, on_log)
    elif backend == "texify":
        return ocr_texify(image_bytes, on_log)
    else:
        raise ValueError(f"Unknown backend: {backend!r}")
