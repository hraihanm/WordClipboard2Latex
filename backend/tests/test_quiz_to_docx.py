"""Tests for quiz markdown -> DOCX export (quiz_to_word.quiz_md_to_docx_bytes).

The DOCX path shells out to Pandoc, so these are integration tests that skip
cleanly when Pandoc is not on PATH.
"""

import io
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from quiz_to_word import quiz_md_to_docx_bytes  # noqa: E402

pytestmark = pytest.mark.skipif(
    shutil.which("pandoc") is None, reason="Pandoc not installed"
)

QUIZ_MD = """## Berapakah nilai $\\int_0^1 x^2\\,dx$?

- (A) $\\frac{1}{2}$
- (B) $\\frac{1}{3}$
- (C) $1$

### Jawaban
B

### Pembahasan
Karena $\\int_0^1 x^2\\,dx = \\frac{1}{3}$.

## Konstanta gravitasi Newton adalah {{1}}.

### Jawaban
1. [numerik:0.01] 6.674e-11
"""


def _document_xml(docx_bytes: bytes) -> str:
    assert docx_bytes[:2] == b"PK", "not a zip/docx"
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
        return z.read("word/document.xml").decode("utf-8", "replace")


def _para_styles(document_xml: str) -> set[str]:
    return {
        chunk.split('w:val="')[1].split('"')[0]
        for chunk in document_xml.split("<w:pStyle ")[1:]
    }


def test_docx_is_styled_and_has_native_math():
    doc = _document_xml(quiz_md_to_docx_bytes(QUIZ_MD))
    styles = _para_styles(doc)
    # Custom styles bind (Pandoc strips spaces from the styleId).
    assert "P-Problem" in styles
    assert "P-Sub-problem" in styles
    assert "Solution-Title" in styles
    # LaTeX math becomes native Word equations (OMML), not literal "$…$".
    assert "<m:oMath" in doc
    assert "Jawaban" in doc  # answer key present by default


def test_worksheet_omits_solutions():
    doc = _document_xml(quiz_md_to_docx_bytes(QUIZ_MD, include_solutions=False))
    styles = _para_styles(doc)
    assert "P-Problem" in styles
    assert "P-Sub-problem" in styles
    # No solution/answer-key content.
    assert "Solution-Title" not in styles
    assert "Blank-Key" not in styles
    assert "Jawaban" not in doc
    # Math in the stem still converts.
    assert "<m:oMath" in doc


def test_empty_markdown_raises():
    with pytest.raises(ValueError):
        quiz_md_to_docx_bytes("")
