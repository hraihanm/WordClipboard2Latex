"""Convert OMML (Office Math Markup Language) to LaTeX via Pandoc."""

from __future__ import annotations

import io
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path

# Minimal document.xml content for the docx zip
_DOCUMENT_XML = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas"
            xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
            xmlns:o="urn:schemas-microsoft-com:office:office"
            xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
            xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"
            xmlns:v="urn:schemas-microsoft-com:vml"
            xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
            xmlns:w10="urn:schemas-microsoft-com:office:word"
            xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"
            xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup"
            xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk"
            xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml"
            xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
            mc:Ignorable="w14 wp14">
  <w:body>
    <w:p>
      {omml}
    </w:p>
  </w:body>
</w:document>
"""

_CONTENT_TYPES_XML = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml"
            ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""

_RELS_XML = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
                Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
                Target="word/document.xml"/>
</Relationships>
"""

_WORD_RELS_XML = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
</Relationships>
"""


def _wrap_bare_text_in_mt(xml: str) -> str:
    r"""Wrap bare text inside <m:r> elements with <m:t> tags.

    In proper OOXML, text content lives in <m:t> inside <m:r>:
        <m:r><m:rPr>...</m:rPr><m:t>text</m:t></m:r>

    But clipboard HTML often has bare text directly in <m:r>:
        <m:r>text</m:r>
        <m:r><m:rPr>...</m:rPr>text</m:r>

    Pandoc requires <m:t> to extract content, so we add it.
    """
    def fix_mr(m: re.Match) -> str:
        inner = m.group(1)
        # Check if already has <m:t> — no fix needed
        if '<m:t>' in inner or '<m:t ' in inner:
            return m.group(0)
        # Split into rPr (if present) and the rest
        rpr_match = re.match(r'(<m:rPr\b.*?</m:rPr>)(.*)', inner, re.DOTALL)
        if rpr_match:
            rpr = rpr_match.group(1)
            text = rpr_match.group(2).strip()
            if text:
                return f'<m:r>{rpr}<m:t>{text}</m:t></m:r>'
            return f'<m:r>{rpr}</m:r>'
        # No rPr — the whole inner content is text
        text = inner.strip()
        if text:
            return f'<m:r><m:t>{text}</m:t></m:r>'
        return '<m:r></m:r>'

    # Match <m:r>...</m:r> blocks (non-greedy)
    return re.sub(r'<m:r\b[^>]*>(.*?)</m:r>', fix_mr, xml, flags=re.DOTALL)


def _strip_html_from_omml(xml: str) -> str:
    """Strip HTML formatting tags that Word mixes into clipboard OMML.

    When Word copies to clipboard as HTML, it wraps OMML content in HTML
    formatting tags like <font>, <span>, <i>, <b>, <br> etc.  These are
    not valid inside .docx XML and cause Pandoc to fail.  We strip them
    while preserving all m: and w: namespace tags and text content.
    """
    # Remove opening and self-closing HTML tags (no namespace prefix)
    # This matches tags like <font ...>, <span ...>, <i ...>, <br>, <br/>, etc.
    xml = re.sub(
        r'<(?:font|span|i|b|u|em|strong|br|div|img|a)\b[^>]*/?>',
        '', xml, flags=re.IGNORECASE,
    )
    # Remove closing HTML tags
    xml = re.sub(
        r'</(?:font|span|i|b|u|em|strong|br|div|img|a)>',
        '', xml, flags=re.IGNORECASE,
    )
    return xml


def _build_docx_bytes(omml_xml: str) -> bytes:
    """Create a minimal .docx (zip) in memory containing the OMML."""
    # Strip HTML formatting tags that Word mixes into clipboard OMML
    # (e.g. <font>, <span>, <i>, <br> wrapping m: elements)
    omml_clean = _strip_html_from_omml(omml_xml)
    # Wrap bare text in <m:r> with <m:t> (clipboard HTML omits <m:t>)
    omml_clean = _wrap_bare_text_in_mt(omml_clean)
    # Strip namespace declarations from the fragment since the envelope provides them
    omml_clean = re.sub(r'\s+xmlns:\w+="[^"]*"', '', omml_clean)
    # BS4's lxml parser lowercases all tag names, but Pandoc needs proper-cased
    # OMML tags. Restore the correct case.
    omml_clean = _restore_omml_case(omml_clean)
    doc_xml = _DOCUMENT_XML.format(omml=omml_clean)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', _CONTENT_TYPES_XML)
        zf.writestr('_rels/.rels', _RELS_XML)
        zf.writestr('word/_rels/document.xml.rels', _WORD_RELS_XML)
        zf.writestr('word/document.xml', doc_xml)
    return buf.getvalue()


def omml_to_latex(omml_xml: str) -> str:
    """Convert an OMML XML fragment to LaTeX math string using Pandoc.

    Args:
        omml_xml: Raw OMML XML (e.g. <m:oMath>...</m:oMath>)

    Returns:
        LaTeX math string (without delimiters like $ or \\[\\])
    """
    docx_bytes = _build_docx_bytes(omml_xml)

    try:
        # Write to a temp file since Pandoc needs a seekable docx
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp:
            tmp.write(docx_bytes)
            tmp_path = tmp.name

        result = subprocess.run(
            ["pandoc", tmp_path, "-f", "docx", "-t", "latex", "--wrap=none"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )

        Path(tmp_path).unlink(missing_ok=True)

        if result.returncode != 0:
            return _fallback_text_extract(omml_xml)

        latex = result.stdout.strip()
        latex = _strip_math_delimiters(latex)
        return latex

    except FileNotFoundError:
        raise RuntimeError(
            "Pandoc is not installed or not on PATH. "
            "Install it from https://pandoc.org/installing.html"
        )
    except subprocess.TimeoutExpired:
        return _fallback_text_extract(omml_xml)


def _strip_math_delimiters(latex: str) -> str:
    """Remove Pandoc's math delimiters to get bare math content."""
    # Remove display math \[...\]
    latex = re.sub(r'^\\\[', '', latex)
    latex = re.sub(r'\\\]$', '', latex)
    # Remove inline math $...$
    if latex.startswith('$') and latex.endswith('$'):
        latex = latex[1:-1]
    # Remove \(...\)
    latex = re.sub(r'^\\\(', '', latex)
    latex = re.sub(r'\\\)$', '', latex)
    return latex.strip()


def _fallback_text_extract(xml: str) -> str:
    """Extract plain text from OMML XML as a last resort."""
    text = re.sub(r'<[^>]+>', '', xml)
    return text.strip()


# Mapping of lowercased OMML/WordML tag names to their proper case.
# These are the standard OOXML math namespace (m:) and wordprocessingml (w:) tags.
_OMML_TAG_CASE = {
    # Math tags (m: namespace)
    "m:omath": "m:oMath",
    "m:omathpara": "m:oMathPara",
    "m:r": "m:r",
    "m:t": "m:t",
    "m:f": "m:f",
    "m:fpr": "m:fPr",
    "m:num": "m:num",
    "m:den": "m:den",
    "m:e": "m:e",
    "m:sub": "m:sub",
    "m:sup": "m:sup",
    "m:ssub": "m:sSub",
    "m:ssup": "m:sSup",
    "m:ssubsup": "m:sSubSup",
    "m:nary": "m:nary",
    "m:narypr": "m:naryPr",
    "m:chr": "m:chr",
    "m:limloc": "m:limLoc",
    "m:limlow": "m:limLow",
    "m:limupp": "m:limUpp",
    "m:lim": "m:lim",
    "m:rad": "m:rad",
    "m:radpr": "m:radPr",
    "m:deghide": "m:degHide",
    "m:deg": "m:deg",
    "m:func": "m:func",
    "m:funcpr": "m:funcPr",
    "m:fname": "m:fName",
    "m:d": "m:d",
    "m:dpr": "m:dPr",
    "m:begchr": "m:begChr",
    "m:endchr": "m:endChr",
    "m:eqarr": "m:eqArr",
    "m:m": "m:m",
    "m:mr": "m:mr",
    "m:mpr": "m:mPr",
    "m:mcs": "m:mcs",
    "m:mc": "m:mc",
    "m:mcpr": "m:mcPr",
    "m:count": "m:count",
    "m:mcjc": "m:mcJc",
    "m:ctrlpr": "m:ctrlPr",
    "m:rpr": "m:rPr",
    "m:sty": "m:sty",
    "m:brk": "m:brk",
    "m:aln": "m:aln",
    "m:bar": "m:bar",
    "m:barpr": "m:barPr",
    "m:pos": "m:pos",
    "m:box": "m:box",
    "m:boxpr": "m:boxPr",
    "m:acc": "m:acc",
    "m:accpr": "m:accPr",
    "m:groupchr": "m:groupChr",
    "m:groupchrpr": "m:groupChrPr",
    "m:borderbox": "m:borderBox",
    "m:borderboxpr": "m:borderBoxPr",
    "m:phantom": "m:phantom",
    "m:phantpr": "m:phantPr",
    "m:val": "m:val",
    # WordprocessingML tags commonly found inside OMML
    "w:rpr": "w:rPr",
    "w:rfonts": "w:rFonts",
    "w:ascii": "w:ascii",
    "w:i": "w:i",
    "w:b": "w:b",
}

# Build a regex that matches namespaced tags in opening/closing/self-closing form.
_OMML_TAG_RE = re.compile(
    r'(</?)'                       # opening < or </
    r'(m:[a-zA-Z]+|w:[a-zA-Z]+)'  # namespaced tag (any case)
    r'(?=[\s/>])',                 # followed by space, /, or >
)

_OMML_ATTR_RE = re.compile(
    r'\s(m:[a-zA-Z]+|w:[a-zA-Z]+)(=)',  # namespaced attribute name
)


def _restore_omml_case(xml: str) -> str:
    """Restore proper case for OMML tag and attribute names after BS4 lowercasing.

    Important: if a tag is already properly cased (e.g. from the placeholder
    extraction path), we must preserve its original case, not lowercase it.
    """
    def replace_tag(m: re.Match) -> str:
        prefix = m.group(1)  # < or </
        tag_original = m.group(2)
        tag_lower = tag_original.lower()
        proper = _OMML_TAG_CASE.get(tag_lower)
        if proper is not None:
            return prefix + proper
        # Not in mapping — keep original case (don't lowercase it)
        return prefix + tag_original

    def replace_attr(m: re.Match) -> str:
        attr_original = m.group(1)
        attr_lower = attr_original.lower()
        proper = _OMML_TAG_CASE.get(attr_lower)
        if proper is not None:
            return ' ' + proper + m.group(2)
        return ' ' + attr_original + m.group(2)

    xml = _OMML_TAG_RE.sub(replace_tag, xml)
    xml = _OMML_ATTR_RE.sub(replace_attr, xml)
    return xml
