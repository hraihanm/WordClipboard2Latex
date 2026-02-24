"""OCR service — Gemini API and GOT-OCR 2.0 backends."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

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

def ocr_gemini(image_bytes: bytes, mime_type: str, fmt: str) -> str:
    import google.genai as genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY environment variable is not set. "
            "Get a key at https://aistudio.google.com/apikey"
        )

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            PROMPTS[fmt],
        ],
    )
    return response.text


# ---------------------------------------------------------------------------
# GOT-OCR 2.0 backend (local, lazy-loaded)
# ---------------------------------------------------------------------------

_got_model = None
_got_tokenizer = None


def _load_got():
    global _got_model, _got_tokenizer
    if _got_model is not None:
        return _got_model, _got_tokenizer

    from transformers import AutoModel, AutoTokenizer

    model_id = "ucaslcl/GOT-OCR2_0"
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    model = AutoModel.from_pretrained(
        model_id,
        trust_remote_code=True,
        low_cpu_mem_usage=True,
        device_map="cuda",
        use_safetensors=True,
        pad_token_id=tokenizer.eos_token_id,
    ).eval()

    _got_model = model
    _got_tokenizer = tokenizer
    return model, tokenizer


def ocr_got(image_bytes: bytes, fmt: str) -> str:
    # GOT-OCR takes a file path, not bytes
    ocr_type = "ocr" if fmt == "text" else "format"
    model, tokenizer = _load_got()

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name

    try:
        return model.chat(tokenizer, tmp_path, ocr_type=ocr_type)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def run_ocr(image_bytes: bytes, mime_type: str, backend: str, fmt: str) -> str:
    if backend == "gemini":
        return ocr_gemini(image_bytes, mime_type, fmt)
    elif backend == "got":
        return ocr_got(image_bytes, fmt)
    else:
        raise ValueError(f"Unknown backend: {backend!r}")
