"""Generate the Pandoc reference-doc template used by quiz -> DOCX export.

Run once to (re)build ``backend/assets/quiz-template.docx``. The template defines
the named paragraph styles that ``quiz_to_word._to_pandoc_custom_style_md`` targets
via ``::: {custom-style="..."}`` fenced divs. Pandoc binds those custom styles to
the same-named styles in this reference doc, so the exported quiz picks up the
fonts / colours / spacing defined here.

Usage (from backend/):
    venv/Scripts/python -m pip install python-docx
    venv/Scripts/python scripts/build_quiz_template.py

python-docx is a *build-time* dependency only (see requirements-dev.txt); the
template is committed as a static asset so the server needs nothing extra.
"""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_LINE_SPACING
from docx.shared import Pt, RGBColor, Inches

OUT = Path(__file__).resolve().parent.parent / "assets" / "quiz-template.docx"

# Body font for the whole document.
BODY_FONT = "Calibri"


def _para_style(doc, name, *, size=11, bold=False, italic=False, color=None,
                left_indent=None, space_before=0, space_after=4,
                keep_with_next=False):
    """Create (or fetch) a paragraph style and apply the given formatting."""
    styles = doc.styles
    try:
        style = styles[name]
    except KeyError:
        style = styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
    style.base_style = styles["Normal"]

    font = style.font
    font.name = BODY_FONT
    font.size = Pt(size)
    font.bold = bold
    font.italic = italic
    if color is not None:
        font.color.rgb = RGBColor(*color)

    pf = style.paragraph_format
    if left_indent is not None:
        pf.left_indent = Inches(left_indent)
    pf.space_before = Pt(space_before)
    pf.space_after = Pt(space_after)
    pf.keep_with_next = keep_with_next
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    return style


def build() -> Path:
    doc = Document()

    # Base body font.
    normal = doc.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(11)

    # Question stem — a touch of space above, kept with the options that follow.
    _para_style(doc, "P - Problem", size=11, bold=True,
                space_before=12, space_after=4, keep_with_next=True)
    # Answer options / essay sub-parts — indented under the stem.
    _para_style(doc, "P - Sub-problem", size=11, left_indent=0.3,
                space_after=2)
    # Bank metadata — small, muted, italic.
    _para_style(doc, "Problem - Meta", size=9, italic=True,
                color=(0x88, 0x88, 0x88), space_before=2, space_after=2)
    # "Jawaban: B" title — bold green, sits above the worked solution.
    _para_style(doc, "Solution - Title", size=11, bold=True,
                color=(0x1B, 0x7F, 0x3B), space_before=6, space_after=2,
                keep_with_next=True)
    # FITB answer-key lines — blue, indented.
    _para_style(doc, "Blank - Key", size=11, color=(0x1D, 0x4E, 0xD8),
                left_indent=0.3, space_after=2)
    # Worked-solution paragraphs — indented, slightly muted.
    _para_style(doc, "Solution", size=11, color=(0x33, 0x33, 0x33),
                left_indent=0.3, space_after=4)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    return OUT


if __name__ == "__main__":
    path = build()
    print(f"Wrote reference template -> {path}")
