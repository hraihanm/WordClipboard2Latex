"""Tests for quiz markdown -> DOCX export (quiz_to_word.quiz_md_to_docx_bytes).

The DOCX path shells out to Pandoc, so these are integration tests that skip
cleanly when Pandoc is not on PATH.
"""

import io
import re
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

```meta
difficulty: 2
cognitive: Applying
```

## Konstanta gravitasi Newton adalah {{1}}.

### Jawaban
1. [numerik:0.01] 6.674e-11
"""


def _document_xml(docx_bytes: bytes) -> str:
    assert docx_bytes[:2] == b"PK", "not a zip/docx"
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
        return z.read("word/document.xml").decode("utf-8", "replace")


def _styles_xml(docx_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
        return z.read("word/styles.xml").decode("utf-8", "replace")


def _has_part(docx_bytes: bytes, name: str) -> bool:
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
        return name in z.namelist()


def _para_styles(document_xml: str) -> set[str]:
    return {
        chunk.split('w:val="')[1].split('"')[0]
        for chunk in document_xml.split("<w:pStyle ")[1:]
    }


def _style_block(styles_xml: str, style_id: str) -> str:
    m = re.search(rf'<w:style [^>]*w:styleId="{style_id}".*?</w:style>', styles_xml, re.S)
    return m.group(0) if m else ""


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
    # Metadata is off by default.
    assert "P-Meta" not in styles


def test_no_baked_numbering():
    """Numbers come from the template's list, not baked into stem text."""
    out = quiz_md_to_docx_bytes(QUIZ_MD)
    doc = _document_xml(out)
    # No P-Problem paragraph starts with a literal "1." / "2." marker.
    for p in re.findall(r"<w:p\b.*?</w:p>", doc, re.S):
        if "P-Problem" in p:
            txt = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p))
            assert not re.match(r"\s*\d+\.\s", txt), f"baked number in: {txt!r}"
    # The template's numbering part is carried through and the style links to it.
    assert _has_part(out, "word/numbering.xml")
    assert "<w:numPr>" in _style_block(_styles_xml(out), "P-Problem")


def test_worksheet_omits_solutions():
    doc = _document_xml(quiz_md_to_docx_bytes(QUIZ_MD, include_solutions=False))
    styles = _para_styles(doc)
    assert "P-Problem" in styles
    assert "P-Sub-problem" in styles
    # No solution/answer-key/metadata content.
    assert "Solution-Title" not in styles
    assert "Solution-Key" not in styles
    assert "P-Meta" not in styles
    assert "Jawaban" not in doc
    # Math in the stem still converts.
    assert "<m:oMath" in doc


def test_metadata_is_hidden_and_opt_in():
    # Off by default.
    assert "P-Meta" not in _para_styles(_document_xml(quiz_md_to_docx_bytes(QUIZ_MD)))
    # Opt-in: appears, in a hidden (vanish) style.
    out = quiz_md_to_docx_bytes(QUIZ_MD, include_meta=True)
    assert "P-Meta" in _para_styles(_document_xml(out))
    assert "<w:vanish" in _style_block(_styles_xml(out), "P-Meta")


def test_fitb_uses_solution_key():
    doc = _document_xml(quiz_md_to_docx_bytes(QUIZ_MD))
    styles = _para_styles(doc)
    assert "Solution-Key" in styles       # FITB answer key has its own style
    assert "Jawaban: Isian" in doc        # FITB answer title


def test_latex_lists_become_word_lists():
    """\\begin{itemize} / \\begin{enumerate} must render as real Word lists."""
    md = (
        "## Soal dengan daftar LaTeX.\n\n"
        "### Pembahasan\n"
        "Langkah-langkah:\n\n"
        "\\begin{enumerate}\n\\item pertama\n\\item kedua\n\\end{enumerate}\n\n"
        "Poin tambahan:\n\n"
        "\\begin{itemize}\n\\item alpha\n\\item beta\n\\end{itemize}\n"
    )
    doc = _document_xml(quiz_md_to_docx_bytes(md))
    assert doc.count("<w:numPr>") >= 4          # four list items, all real list paras
    texts = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", doc))
    for item in ("pertama", "kedua", "alpha", "beta"):
        assert item in texts, f"list item dropped: {item}"


def test_empty_markdown_raises():
    with pytest.raises(ValueError):
        quiz_md_to_docx_bytes("")


def test_thematic_break_in_solution_survives():
    """A `---` rule in a solution body must not be misread as a YAML block."""
    md = (
        "## Soal dengan garis pemisah?\n\n"
        "- (A) x\n- (B) y\n\n"
        "### Jawaban\nA\n\n"
        "### Pembahasan\nBagian pertama.\n\n---\n\nBagian kedua."
    )
    out = quiz_md_to_docx_bytes(md)
    assert out[:2] == b"PK"


# --- endpoint (multipart) --------------------------------------------------

def _client():
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


def test_endpoint_worksheet_multipart():
    r = _client().post(
        "/api/quiz/to-docx",
        data={"text": QUIZ_MD, "include_solutions": "false", "filename": "my sheet"},
    )
    assert r.status_code == 200
    assert r.content[:2] == b"PK"
    assert 'filename="my sheet.docx"' in r.headers.get("content-disposition", "")
    styles = _para_styles(_document_xml(r.content))
    assert "Solution-Title" not in styles  # worksheet drops solutions


def test_endpoint_include_meta_flag():
    r = _client().post(
        "/api/quiz/to-docx",
        data={"text": QUIZ_MD, "include_meta": "true"},
    )
    assert r.status_code == 200
    assert "P-Meta" in _para_styles(_document_xml(r.content))


def test_endpoint_uploaded_template_overrides():
    from quiz_to_word import _DEFAULT_TEMPLATE
    tpl = _DEFAULT_TEMPLATE.read_bytes()
    r = _client().post(
        "/api/quiz/to-docx",
        data={"text": QUIZ_MD, "filename": "custom"},
        files={"template": ("mine.docx", tpl, "application/octet-stream")},
    )
    assert r.status_code == 200
    assert r.content[:2] == b"PK"


def test_endpoint_rejects_non_docx_template():
    r = _client().post(
        "/api/quiz/to-docx",
        data={"text": QUIZ_MD},
        files={"template": ("bad.docx", b"not a zip", "application/octet-stream")},
    )
    assert r.status_code == 400
