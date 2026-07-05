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

# Pandoc input format: math delimiters + raw LaTeX pass-through.
# raw_tex lets pandoc handle \textbf{}, \emph{}, \begin{enumerate}[(a)] etc. in text.
# -smart keeps ASCII quotes/apostrophes verbatim so BANK_META JSON survives and
# prose apostrophes (Newton's) don't become curly Unicode on the round trip.
# -yaml_metadata_block stops Pandoc from treating a `---` thematic break in a
# stem/solution (or between questions) as a YAML front-matter block, which would
# otherwise abort the whole conversion with a YAML parse error.
_MD_FMT = (
    "markdown-smart-yaml_metadata_block"
    "+tex_math_dollars+tex_math_single_backslash+raw_tex"
)

# Bundled Pandoc reference-doc that defines the named paragraph styles
# ("P - Problem", "Solution - Title", …). Regenerate with
# scripts/build_quiz_template.py. Used by default so exports are styled without
# the caller having to supply a template.
_DEFAULT_TEMPLATE = Path(__file__).resolve().parent / "assets" / "quiz-template.docx"

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
p.Solution-Key,li.Solution-Key,div.Solution-Key
  {mso-style-name:"Solution - Key";}
p.P-Meta,li.P-Meta,div.P-Meta
  {mso-style-name:"P - Meta";color:gray;font-size:9.0pt;mso-style-hidden:yes;}
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

# Matches an innermost itemize/enumerate environment (no nested begin inside).
_LATEX_LIST_RE = re.compile(
    r"\\begin\{(itemize|enumerate)\}(.*?)\\end\{\1\}",
    re.DOTALL,
)


def _latex_lists_to_md(text: str) -> str:
    """Rewrite LaTeX ``itemize`` / ``enumerate`` environments to markdown lists.

    Pandoc drops raw-tex list environments when producing DOCX, so LaTeX-authored
    lists would silently vanish.  Convert them to markdown ``-`` / ``1.`` lists
    (which Pandoc renders as real Word lists) *before* handing text to Pandoc.
    Works inside-out so nested lists convert too; the whole list is fenced by
    blank lines so the surrounding paragraph splitter keeps it intact.
    """
    def _one(m: re.Match) -> str:
        kind, inner = m.group(1), m.group(2)
        # Split on \item; drop the empty head before the first \item.
        raw_items = re.split(r"\\item\b", inner)[1:]
        lines: list[str] = []
        for i, it in enumerate(raw_items, 1):
            # \item[label] — keep the optional label inline.
            it = re.sub(r"^\s*\[([^\]]*)\]", r"\1 ", it)
            body = " ".join(seg.strip() for seg in it.strip().splitlines() if seg.strip())
            if not body:
                continue
            marker = f"{i}." if kind == "enumerate" else "-"
            lines.append(f"{marker} {body}")
        return "\n\n" + "\n".join(lines) + "\n\n" if lines else ""

    prev = None
    out = text
    # Repeat until stable so nested environments (inner first) all convert.
    while prev != out:
        prev = out
        out = _LATEX_LIST_RE.sub(_one, out)
    return out


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
    text = _latex_lists_to_md(text)
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
    body = _latex_lists_to_md(solution_body)
    body = _preprocess_math_spacing(body, "markdown")
    raw = _pandoc(body, _MD_FMT, "html", ["--mathml", "--wrap=none"])
    raw = _fix_math_spacing(raw)
    # Annotate every <p> and <li> tag
    annotated = re.sub(r"<p(?:\s[^>]*)?>",  '<p class="Solution">',  raw, flags=re.IGNORECASE)
    annotated = re.sub(r"<li(?:\s[^>]*)?>", '<li class="Solution">', annotated, flags=re.IGNORECASE)
    return annotated.strip()


# ---------------------------------------------------------------------------
# HTML body builder
# ---------------------------------------------------------------------------

def questions_to_word_html(
    questions: list[QuizQuestion],
    include_meta: bool = False,
) -> str:
    """Build the CF_HTML body fragment for a list of QuizQuestion objects.

    ``include_meta`` — when True, append the BANK_META line in the hidden
    ``P - Meta`` style *after* the solution (invisible in print, kept for
    round-tripping). Omitted entirely otherwise.
    """
    parts: list[str] = []

    for q in questions:
        if q.stem:
            parts.append(_para_to_html(q.stem, "P-Problem"))

        # Options (mc/cmc) and essay subparts are both authored as `### ` and
        # share the P-Sub-problem style; only one list is ever populated.
        for opt in q.options:
            parts.append(_para_to_html(opt, "P-Sub-problem"))
        for sub in q.subparts:
            parts.append(_para_to_html(sub, "P-Sub-problem"))

        parts.append(
            f'<p class="Solution-Title">{_answer_title(q)}</p>'
        )

        # fill-in-the-blank answer keys get their own style so they survive the
        # round trip (a P-Sub-problem here would be read back as an option).
        for b in q.blanks:
            parts.append(_para_to_html(b, "Solution-Key"))

        if q.solution_body:
            parts.append(_solution_body_to_html(q.solution_body))

        # Hidden metadata sits last, after the solution.
        if include_meta and q.meta:
            parts.append(_para_to_html(q.meta, "P-Meta"))

    return "\n".join(parts)


def _answer_title(q: "QuizQuestion") -> str:
    """The text of the Solution-Title paragraph for a question."""
    if q.qtype == "essay":
        return "Solusi"
    if q.qtype == "fitb":
        return "Jawaban: Isian"
    if q.qtype == "cmc":
        return "Jawaban: " + ", ".join(q.answer_labels)
    return f"Jawaban: {q.answer_label}"


# ---------------------------------------------------------------------------
# Clipboard path
# ---------------------------------------------------------------------------

def quiz_md_to_clipboard(quiz_md: str, include_meta: bool = False) -> dict:
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

    html_body = questions_to_word_html(questions, include_meta=include_meta)
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


def _to_pandoc_custom_style_md(
    questions: list[QuizQuestion],
    include_solutions: bool = True,
    include_meta: bool = False,
) -> str:
    """Render questions as Pandoc extended markdown with custom-style fenced divs.

    When Pandoc processes this with --reference-doc=template.docx the fenced-div
    style names map to these named paragraph styles in the template:

      "P - Problem"     ← problem stem (auto-numbered by the template's list)
      "P - Sub-problem" ← each answer option / essay sub-part (auto-lettered)
      "Solution - Title"← Jawaban line
      "Solution - Key"  ← FITB answer-key lines
      "Solution"        ← solution body paragraphs
      "P - Meta"        ← BANK_META block (hidden style, opt-in, after solution)

    Numbering is produced by the template's style-linked list, so **no** number
    is baked into the text.  Without a reference doc Pandoc creates the styles
    from scratch (no numbering / formatting, but math still converts to OMML).

    include_solutions:
        When False, emit a clean worksheet: stems + options only (answer title,
        FITB keys, worked solution and metadata all omitted).
    include_meta:
        When True (and solutions are included), append the hidden BANK_META line
        after the solution.  Omitted otherwise.
    """
    blocks: list[str] = []

    for q in questions:
        if q.stem:
            stem = _latex_lists_to_md(q.stem)
            blocks.append(f'::: {{custom-style="P - Problem"}}\n{stem}\n:::')

        for opt in q.options:
            opt = _latex_lists_to_md(opt)
            blocks.append(f'::: {{custom-style="P - Sub-problem"}}\n{opt}\n:::')
        for sub in q.subparts:
            sub = _latex_lists_to_md(sub)
            blocks.append(f'::: {{custom-style="P - Sub-problem"}}\n{sub}\n:::')

        if not include_solutions:
            # Worksheet mode: stem + options only.
            continue

        blocks.append(
            f'::: {{custom-style="Solution - Title"}}\n'
            f'**{_answer_title(q)}**\n'
            f':::'
        )

        for b in q.blanks:
            blocks.append(f'::: {{custom-style="Solution - Key"}}\n{b}\n:::')

        if q.solution_body:
            # Wrap each non-empty paragraph in a Solution div.
            body = _latex_lists_to_md(q.solution_body)
            for para in re.split(r"\n{2,}", body):
                para = para.strip()
                if para:
                    blocks.append(f'::: {{custom-style="Solution"}}\n{para}\n:::')

        # Hidden metadata sits last, after the solution.
        if include_meta and q.meta:
            blocks.append(f'::: {{custom-style="P - Meta"}}\n{q.meta}\n:::')

    return "\n\n".join(blocks)


def quiz_md_to_docx_bytes(
    quiz_md: str,
    reference_doc: str | None = None,
    include_solutions: bool = True,
    use_template: bool = True,
    include_meta: bool = False,
) -> bytes:
    """Convert quiz markdown to DOCX bytes.

    Parameters
    ----------
    quiz_md:
        Quiz markdown in astro-dev-id format.
    reference_doc:
        Path to a .docx template that defines the paragraph styles
        "P - Problem", "P - Sub-problem", "Solution - Title", "Solution - Key",
        "P - Meta" and "Solution". If None and ``use_template`` is True,
        the bundled ``assets/quiz-template.docx`` is used. Pass an explicit path
        to override it.
    include_solutions:
        When False, export a clean worksheet (stems + options only).
    use_template:
        When False, skip the reference doc entirely (Pandoc default styling;
        math still converts to OMML). Ignored when ``reference_doc`` is given.
    include_meta:
        When True, append the hidden BANK_META line after each solution.

    Returns
    -------
    bytes
        Raw .docx file content.
    """
    questions = parse_quiz_md(quiz_md)
    if not questions:
        raise ValueError("No questions found in the provided quiz markdown.")

    pandoc_md = _to_pandoc_custom_style_md(
        questions,
        include_solutions=include_solutions,
        include_meta=include_meta,
    )

    # Resolve the reference doc: explicit path > bundled default (unless opted out).
    ref: str | None = reference_doc
    if ref is None and use_template and _DEFAULT_TEMPLATE.is_file():
        ref = str(_DEFAULT_TEMPLATE)

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        args = ["-o", str(tmp_path)]
        if ref:
            args += ["--reference-doc", ref]

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
