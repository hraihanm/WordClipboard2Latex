"""Convert quiz markdown (astro-dev-id format) to Word clipboard or DOCX.

Word → quiz markdown is handled by quiz_parser.py.  This module covers
the reverse: quiz markdown → Word.

Two output paths
----------------
Clipboard (CF_HTML)
    Builds a CF_HTML blob where each section of the question is wrapped
    in <p class="P-Problem">, <p class="P-Sub-problem">, etc.  Word maps
    these class names to named paragraph styles on paste.  Math is
    converted to MathML via Pandoc (same strategy as to_clipboard.py).

DOCX (Pandoc custom-style markdown)
    Rewrites the quiz markdown into Pandoc's extended markdown using
    ::: {custom-style="..."} fenced divs, then calls Pandoc with
    --reference-doc=<template> to produce a .docx with the correct
    paragraph styles.  Without a reference doc the styles fall back to
    Heading 2 / Heading 3 (math still works).
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from quiz_parser import QuizQuestion, parse_quiz_md
from to_clipboard import (
    CF_HTML_FORMAT,
    _CF_HTML_HEADER_TEMPLATE,
    _pandoc,
    _preprocess_math_spacing,
)

# Pandoc input format for markdown+LaTeX math
_MD_FMT = "markdown+tex_math_dollars+tex_math_single_backslash"

# Matches a single Pandoc-generated <p> wrapper (including attributes Pandoc may add)
_P_OPEN_RE = re.compile(r"^<p(?:\s[^>]*)?>", re.IGNORECASE)

# Matches </math> followed by any whitespace (including newlines Pandoc may insert)
_MATH_CLOSE_RE = re.compile(r"(</math>)\s+", re.IGNORECASE)

# ---------------------------------------------------------------------------
# MSO-style CF_HTML builder
# ---------------------------------------------------------------------------

# Word maps HTML class names to named paragraph styles only when
# mso-style-name declarations are present in a <style> block.  Without them
# everything falls back to "Normal" regardless of the class attribute.
_QUIZ_MSO_STYLES = """\
<style>
<!--
p.P-Problem,li.P-Problem,div.P-Problem
  {mso-style-name:"P - Problem";}
p.P-Sub-problem,li.P-Sub-problem,div.P-Sub-problem
  {mso-style-name:"P - Sub-problem";}
p.Solution-Title,li.Solution-Title,div.Solution-Title
  {mso-style-name:"Solution - Title";font-weight:bold;mso-bidi-font-weight:normal;}
p.Solution,li.Solution,div.Solution
  {mso-style-name:"Solution";}
-->
</style>
"""

_HTML_HEAD = (
    '<html xmlns:o="urn:schemas-microsoft-com:office:office"'
    ' xmlns:w="urn:schemas-microsoft-com:office:word"'
    ' xmlns="http://www.w3.org/TR/REC-html40">'
    '<head>'
    '<meta http-equiv="Content-Type" content="text/html; charset=utf-8">'
    '<meta name="ProgId" content="Word.Document">'
    '<meta name="Generator" content="Microsoft Word 15">'
    + _QUIZ_MSO_STYLES
    + '</head>'
    '<body lang="IN" style="tab-interval:.5in;word-wrap:break-word">'
)
_SF_OPEN   = b"<!--StartFragment-->"
_EF_CLOSE  = b"<!--EndFragment--></body></html>"


def _make_quiz_cf_html(fragment: str) -> bytes:
    """Build a CF_HTML blob with MSO style definitions in <head>.

    The <style> block tells Word which CSS class names map to which named
    paragraph styles, allowing paste to apply P-Problem / P-Sub-problem /
    Solution-Title / Solution styles even if the document doesn't already
    define them.
    """
    dummy = _CF_HTML_HEADER_TEMPLATE.format(sh=0, eh=0, sf=0, ef=0)
    header_len = len(dummy.encode("utf-8"))

    head_bytes = _HTML_HEAD.encode("utf-8")
    frag_bytes = fragment.encode("utf-8")

    sh = header_len
    sf = sh + len(head_bytes) + len(_SF_OPEN)
    ef = sf + len(frag_bytes)
    eh = ef + len(_EF_CLOSE)

    header = _CF_HTML_HEADER_TEMPLATE.format(sh=sh, eh=eh, sf=sf, ef=ef)
    return header.encode("utf-8") + head_bytes + _SF_OPEN + frag_bytes + _EF_CLOSE


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fix_math_spacing(html: str) -> str:
    """Replace whitespace after </math> with a non-breaking space entity.

    Word's MathML→OMML conversion during paste strips bare whitespace that
    immediately follows a </math> closing tag.  &#160; (U+00A0 non-breaking
    space) is an explicit HTML entity, not bare whitespace, so Word preserves
    it through the conversion.  The visual result is identical to a regular
    space for LTR text.
    """
    return _MATH_CLOSE_RE.sub(r'\1&#160;', html)


def _para_to_html(text: str, css_class: str) -> str:
    """Convert a single-paragraph markdown/LaTeX fragment to a styled <p>.

    Calls Pandoc to handle inline math ($...$) → MathML, then replaces
    Pandoc's generic <p> wrapper with one that carries the correct Word
    paragraph-style class.
    """
    text = _preprocess_math_spacing(text, "markdown")
    raw = _pandoc(text, _MD_FMT, "html", ["--mathml", "--wrap=none"]).strip()
    raw = _fix_math_spacing(raw)
    # Replace Pandoc's outer <p> with the class-annotated version
    raw = _P_OPEN_RE.sub(f'<p class="{css_class}">', raw, count=1)
    # If Pandoc didn't wrap in <p> at all (bare inline fragment), do it ourselves
    if not raw.lower().startswith("<p"):
        raw = f'<p class="{css_class}">{raw}</p>'
    return raw


def _solution_body_to_html(solution_body: str) -> str:
    """Convert the full solution body to HTML with Solution paragraph/list classes.

    Processes the body in one Pandoc call so multi-paragraph solutions and
    display-math blocks ($$...$$) are handled correctly.  Annotates every
    <p> and <li> with class="Solution" so Word applies the named style to
    both plain paragraphs and list items.
    """
    body = _preprocess_math_spacing(solution_body, "markdown")
    raw = _pandoc(body, _MD_FMT, "html", ["--mathml", "--wrap=none"])
    raw = _fix_math_spacing(raw)
    # Annotate every <p> and <li> tag
    annotated = re.sub(r"<p(?:\s[^>]*)?>",  '<p class="Solution">',  raw, flags=re.IGNORECASE)
    annotated = re.sub(r"<li(?:\s[^>]*)?>", '<li class="Solution">', annotated, flags=re.IGNORECASE)
    return annotated.strip()


# ---------------------------------------------------------------------------
# HTML body builder
# ---------------------------------------------------------------------------

def questions_to_word_html(questions: list[QuizQuestion]) -> str:
    """Build the CF_HTML body fragment for a list of QuizQuestion objects."""
    parts: list[str] = []

    for q in questions:
        if q.stem:
            parts.append(_para_to_html(q.stem, "P-Problem"))

        for opt in q.options:
            parts.append(_para_to_html(opt, "P-Sub-problem"))

        if q.answer_label:
            parts.append(
                f'<p class="Solution-Title">Jawaban: {q.answer_label}</p>'
            )

        if q.solution_body:
            parts.append(_solution_body_to_html(q.solution_body))

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Clipboard path
# ---------------------------------------------------------------------------

def quiz_md_to_clipboard(quiz_md: str) -> dict:
    """Parse quiz markdown and write Word-styled HTML to the Windows clipboard.

    Returns
    -------
    dict
        ``{"question_count": N, "formats_written": ["HTML"], "warnings": [...]}``
    """
    import win32clipboard

    questions = parse_quiz_md(quiz_md)
    if not questions:
        return {
            "question_count": 0,
            "formats_written": [],
            "warnings": ["No questions found in the provided quiz markdown."],
        }

    html_body = questions_to_word_html(questions)
    cf_html = _make_quiz_cf_html(html_body)

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(CF_HTML_FORMAT, cf_html)
    finally:
        win32clipboard.CloseClipboard()

    return {
        "question_count": len(questions),
        "formats_written": ["HTML"],
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# DOCX path
# ---------------------------------------------------------------------------

_OPTION_LETTERS = "ABCDE"


def _to_pandoc_custom_style_md(questions: list[QuizQuestion]) -> str:
    """Render questions as Pandoc extended markdown with custom-style fenced divs.

    When Pandoc processes this with --reference-doc=template.docx the fenced-div
    style names map to these named paragraph styles in the template:

      "P - Problem"     ← problem stem
      "P - Sub-problem" ← each answer option
      "Solution - Title"← Jawaban line
      "Solution"        ← solution body paragraphs

    Without a reference doc Pandoc creates the styles from scratch (no special
    formatting, but math still converts to OMML correctly).
    """
    blocks: list[str] = []

    for q in questions:
        if q.stem:
            blocks.append(f'::: {{custom-style="P - Problem"}}\n{q.stem}\n:::')

        for opt in q.options:
            blocks.append(f'::: {{custom-style="P - Sub-problem"}}\n{opt}\n:::')

        if q.answer_label:
            blocks.append(
                f'::: {{custom-style="Solution - Title"}}\n'
                f'**Jawaban: {q.answer_label}**\n'
                f':::'
            )

        if q.solution_body:
            # Wrap each non-empty paragraph in a Solution div
            for para in re.split(r"\n{2,}", q.solution_body):
                para = para.strip()
                if para:
                    blocks.append(f'::: {{custom-style="Solution"}}\n{para}\n:::')

    return "\n\n".join(blocks)


def quiz_md_to_docx_bytes(quiz_md: str, reference_doc: str | None = None) -> bytes:
    """Convert quiz markdown to DOCX bytes.

    Parameters
    ----------
    quiz_md:
        Quiz markdown in astro-dev-id format.
    reference_doc:
        Path to a .docx template that defines the paragraph styles
        "P - Problem", "P - Sub-problem", "Solution - Title", and "Solution".
        If None, Pandoc creates those styles from scratch (math converts
        correctly; paragraph formatting will be unstyled).

    Returns
    -------
    bytes
        Raw .docx file content.
    """
    questions = parse_quiz_md(quiz_md)
    if not questions:
        raise ValueError("No questions found in the provided quiz markdown.")

    pandoc_md = _to_pandoc_custom_style_md(questions)

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        args = ["-o", str(tmp_path)]
        if reference_doc:
            args += ["--reference-doc", reference_doc]

        result = subprocess.run(
            ["pandoc", "-f", _MD_FMT, "-t", "docx", *args],
            input=pandoc_md.encode("utf-8"),
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(stderr or f"Pandoc exited with code {result.returncode}")

        return tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)
