"""Generate the Pandoc reference-doc template used by quiz -> DOCX export.

Run once to (re)build ``backend/assets/quiz-template.docx``. The template defines
the named paragraph styles that ``quiz_to_word._to_pandoc_custom_style_md`` targets
via ``::: {custom-style="..."}`` fenced divs. Pandoc binds those custom styles to
the same-named styles in this reference doc, so the exported quiz picks up the
fonts / colours / spacing / indents defined here.

Style taxonomy
--------------
Two prefixes mark the two halves of a problem, matching the house template:

  Problem side  ``P - Subject``  ``P - Problem``  ``P - Sub-problem``
                ``P - Sub-sub Problem``  ``P - Passage``  ``P - Meta``
  Solution side ``Solution - Title``  ``Solution``  ``Solution - Key``
                ``Solution - Step``

Auto-numbering
--------------
``P - Problem`` / ``P - Sub-problem`` / ``P - Sub-sub Problem`` carry *style-linked*
list numbering (``1.`` -> ``a.`` -> ``i.``) via a multilevel list in
``numbering.xml``. Pandoc preserves the reference doc's numbering and applies the
style's ``numPr`` to every paragraph that uses the style, so numbers are produced
by Word (and reset per problem) — the exporter emits **no** baked-in number text.

Hidden metadata
---------------
``P - Meta`` is a *hidden* style (``w:vanish``): when the exporter includes it
(opt-in), the ``BANK_META`` line sits after the solution, invisible in print but
present for round-tripping. Toggle "show hidden text" in Word to see it.

Identity note: python-docx derives the ``w:styleId`` by stripping spaces from the
style *name* — exactly how Pandoc references custom styles. So ``"P - Problem"``
binds to styleId ``P-Problem``. Keep the spaced names here.

Usage (from backend/):
    venv/Scripts/python -m pip install python-docx
    venv/Scripts/python scripts/build_quiz_template.py

python-docx is a *build-time* dependency only (see requirements-dev.txt); the
template is committed as a static asset so the server needs nothing extra.
"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

OUT = Path(__file__).resolve().parent.parent / "assets" / "quiz-template.docx"

# --- House palette / fonts (from the canonical Paket Soal .docx) -----------
# Body font matches the reference doc (Latin Modern Roman). If a target machine
# lacks it, Word substitutes gracefully; swap to "Calibri"/"Cambria" here to
# change the whole document in one place. Math stays on Cambria Math (Word's
# default math font, always installed) — matching the reference doc's mathPr.
BODY_FONT = "LM Roman 10"

ACCENT = RGBColor(0x2F, 0x54, 0x96)    # problems / options / answer title (accent1 -50%)
SOLUTION = RGBColor(0x1F, 0x38, 0x64)  # worked-solution body / keys (accent1 -75%)
META = RGBColor(0x80, 0x80, 0x80)      # muted metadata
INK = RGBColor(0x1A, 0x1A, 0x1A)       # near-black for reading passages

# numId that the three problem-hierarchy styles reference.
LIST_NUM_ID = 1


def _para_style(doc, name, *, size=10, bold=False, italic=False, hidden=False,
                color=None, left_indent=None, hanging=None, space_before=0,
                space_after=6, keep_with_next=False, ilvl=None,
                align=WD_ALIGN_PARAGRAPH.JUSTIFY):
    """Create (or fetch) a paragraph style and apply the given formatting.

    ``hanging`` (inches) makes a hanging indent (room for the list marker).
    ``ilvl`` (0-based) links the style to the shared multilevel list at that
    level, so paragraphs using it auto-number.
    ``hidden`` marks the run font ``w:vanish`` (hidden text).
    """
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
    font.hidden = hidden
    if color is not None:
        font.color.rgb = color

    pf = style.paragraph_format
    if left_indent is not None:
        pf.left_indent = Inches(left_indent)
    if hanging is not None:
        pf.first_line_indent = Inches(-hanging)
    pf.space_before = Pt(space_before)
    pf.space_after = Pt(space_after)
    pf.keep_with_next = keep_with_next
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    if align is not None:
        pf.alignment = align

    if ilvl is not None:
        pPr = style.element.get_or_add_pPr()
        # drop any existing numPr, then add ours
        for old in pPr.findall(qn("w:numPr")):
            pPr.remove(old)
        numPr = OxmlElement("w:numPr")
        il = OxmlElement("w:ilvl"); il.set(qn("w:val"), str(ilvl)); numPr.append(il)
        nid = OxmlElement("w:numId"); nid.set(qn("w:val"), str(LIST_NUM_ID)); numPr.append(nid)
        pPr.append(numPr)
    return style


def build() -> Path:
    doc = Document()

    # Base body font: 10pt LM Roman, justified — matches the reference Normal.
    normal = doc.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(10)
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    normal.paragraph_format.space_after = Pt(6)

    # --- Problem side ------------------------------------------------------
    # Section header ("Soal", or a topic name). 12pt bold, unnumbered.
    _para_style(doc, "P - Subject", size=12, bold=True, color=ACCENT,
                space_before=12, space_after=6, keep_with_next=True)
    # Numbered question stem — auto "1." (list level 0), tight above its options.
    _para_style(doc, "P - Problem", color=ACCENT, ilvl=0,
                left_indent=0.25, hanging=0.25,
                space_before=6, space_after=0, keep_with_next=True)
    # Answer options (mc/cmc) / essay sub-parts — auto "a." (level 1).
    _para_style(doc, "P - Sub-problem", color=ACCENT, ilvl=1,
                left_indent=0.5, hanging=0.25, space_after=0)
    # Nested sub-parts — auto "i." (level 2).
    _para_style(doc, "P - Sub-sub Problem", color=ACCENT, ilvl=2,
                left_indent=0.75, hanging=0.25, space_after=0)
    # Reading passage / context block — near-black for legibility, unnumbered.
    _para_style(doc, "P - Passage", color=INK,
                left_indent=0.25, space_before=6, space_after=6)
    # Bank metadata — small, muted, italic, and HIDDEN; sits after the solution
    # when opted in (invisible in print, kept for round-tripping).
    _para_style(doc, "P - Meta", size=9, italic=True, hidden=True, color=META,
                left_indent=0.25, space_before=2, space_after=2)

    # --- Solution side -----------------------------------------------------
    # "Jawaban: B" title — bold blue, kept with the solution that follows.
    _para_style(doc, "Solution - Title", bold=True, color=ACCENT,
                left_indent=0.25, space_before=6, space_after=6,
                keep_with_next=True)
    # Worked-solution paragraphs — darker blue, indented under the title.
    _para_style(doc, "Solution", color=SOLUTION,
                left_indent=0.25, space_before=6, space_after=6)
    # FITB answer-key lines — bold darker-blue, so they read as answers and
    # never round-trip back as options.
    _para_style(doc, "Solution - Key", bold=True, color=SOLUTION,
                left_indent=0.25, space_after=2)
    # Numbered solution step — available for manual use (or markdown "1." lists).
    _para_style(doc, "Solution - Step", color=SOLUTION,
                left_indent=0.35, space_after=2)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    _inject_numbering(OUT)
    return OUT


# ---------------------------------------------------------------------------
# numbering.xml injection (python-docx can't author list definitions natively)
# ---------------------------------------------------------------------------

_NUMBERING_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:abstractNum w:abstractNumId="0">
    <w:multiLevelType w:val="multilevel"/>
    <w:lvl w:ilvl="0">
      <w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/>
      <w:lvlJc w:val="left"/><w:pPr><w:ind w:left="360" w:hanging="360"/></w:pPr>
    </w:lvl>
    <w:lvl w:ilvl="1">
      <w:start w:val="1"/><w:numFmt w:val="lowerLetter"/><w:lvlText w:val="%2."/>
      <w:lvlJc w:val="left"/><w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr>
    </w:lvl>
    <w:lvl w:ilvl="2">
      <w:start w:val="1"/><w:numFmt w:val="lowerRoman"/><w:lvlText w:val="%3."/>
      <w:lvlJc w:val="left"/><w:pPr><w:ind w:left="1080" w:hanging="360"/></w:pPr>
    </w:lvl>
  </w:abstractNum>
  <w:num w:numId="{num_id}"><w:abstractNumId w:val="0"/></w:num>
</w:numbering>""".format(num_id=LIST_NUM_ID)


def _inject_numbering(path: Path) -> None:
    """Add word/numbering.xml + its content-type and relationship to the docx."""
    with zipfile.ZipFile(path) as zin:
        data = {n: zin.read(n) for n in zin.namelist()}

    data["word/numbering.xml"] = _NUMBERING_XML.encode("utf-8")

    ct = data["[Content_Types].xml"].decode("utf-8")
    if "numbering+xml" not in ct:
        ct = ct.replace(
            "</Types>",
            '<Override PartName="/word/numbering.xml" ContentType='
            '"application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/></Types>',
        )
    data["[Content_Types].xml"] = ct.encode("utf-8")

    rels_name = "word/_rels/document.xml.rels"
    rels = data[rels_name].decode("utf-8")
    if "numbering.xml" not in rels:
        rels = rels.replace(
            "</Relationships>",
            '<Relationship Id="rIdNumbering" Type='
            '"http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" '
            'Target="numbering.xml"/></Relationships>',
        )
    data[rels_name] = rels.encode("utf-8")

    tmp = path.with_suffix(".tmp.docx")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for n, d in data.items():
            zout.writestr(n, d)
    shutil.move(str(tmp), str(path))


if __name__ == "__main__":
    path = build()
    print(f"Wrote reference template -> {path}")
