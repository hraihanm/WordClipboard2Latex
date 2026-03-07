"""Parse clipboard HTML and extract document structure with OMML equations."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from bs4 import BeautifulSoup, NavigableString, Tag


class NodeType(str, Enum):
    TEXT = "text"
    INLINE_MATH = "inline_math"
    DISPLAY_MATH = "display_math"
    HEADING = "heading"
    LIST = "list"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    CODE_LINE = "code_line"  # intermediate: monospace <p>, grouped into code blocks


@dataclass
class DocNode:
    type: NodeType
    content: str = ""
    level: int = 0  # heading level, list nesting
    children: list[DocNode] = field(default_factory=list)
    omml_xml: str = ""  # raw OMML XML for math nodes
    html: str = ""  # raw inner HTML for text nodes
    list_ordered: bool = False
    math_env: str = ""  # "aligned", "pmatrix", "cases", ""
    table_rows: list[list[list["DocNode"]]] = field(default_factory=list)  # rows → cells → nodes


# Regex to detect Word heading classes like MsoHeading1, MsoHeading2, etc.
HEADING_RE = re.compile(r"MsoHeading(\d)", re.IGNORECASE)

# HTML tags that represent inline formatting and should be preserved as-is
_FORMATTING_TAGS = {"b", "strong", "i", "em", "u", "sup", "sub", "s", "strike"}

# Monospace font names that indicate code content (case-insensitive substrings)
_MONOSPACE_FONTS = frozenset({
    "courier new", "courier", "consolas", "monaco",
    "lucida console", "lucida sans typewriter", "monospace", "inconsolata",
})

# Placeholder used to survive HTML parsing: replaces each space in
# mso-spacerun:yes spans before feeding to BS4/lxml.
# lxml strips all C0 control characters (0x00–0x1F), so we use a Unicode
# Private Use Area codepoint (U+E000) that lxml preserves and that never
# legitimately appears in Word document text.
_INDENT_MARKER = "\ue000"

# Matches the FULL content of a mso-spacerun:yes span (spaces + stray newlines)
_SPACERUN_RE = re.compile(
    r'(<span[^>]+mso-spacerun[^>]*>)([ \t\n\r]*)(</span>)',
    re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# Conditional comment unwrapping
# ---------------------------------------------------------------------------

# Regex to extract OMML from Word conditional comments.
# Matches: <!--[if gte msEquation 12]> ... <![endif]-->
_OMML_CONDITIONAL_RE = re.compile(
    r'<!--\[if\s+gte\s+msEquation\s+\d+\]>(.*?)<!\[endif\]-->',
    re.DOTALL | re.IGNORECASE,
)

# Regex to strip the fallback (non-equation) conditional comment blocks.
# Matches: <!--[if !msEquation]> ... <![endif]-->
_FALLBACK_CONDITIONAL_RE = re.compile(
    r'<!--\[if\s+!msEquation\]>.*?<!\[endif\]-->',
    re.DOTALL | re.IGNORECASE,
)

# Regex to strip all remaining conditional comments (VML, supportedlists, etc.)
# This catches <!--[if gte vml 1]>...<![endif]--> and similar.
_REMAINING_CONDITIONAL_RE = re.compile(
    r'<!--\[if\s[^\]]*\]>.*?<!\[endif\]-->',
    re.DOTALL,
)


def _unwrap_omml_conditionals(html: str) -> str:
    """Unwrap OMML from Word conditional comments and strip the rest."""
    # Unwrap OMML equations (keep inner content)
    html = _OMML_CONDITIONAL_RE.sub(r'\1', html)
    # Strip OMML fallback blocks
    html = _FALLBACK_CONDITIONAL_RE.sub('', html)
    # Strip all remaining conditional comments (VML images, etc.)
    html = _REMAINING_CONDITIONAL_RE.sub('', html)
    return html


# ---------------------------------------------------------------------------
# OMML placeholder extraction — the key to avoiding BS4 mangling
# ---------------------------------------------------------------------------

# Match <m:oMathPara ...>...</m:oMathPara> (display math blocks)
_OMATHPARA_RE = re.compile(
    r'(<m:oMathPara\b[^>]*>.*?</m:oMathPara>)',
    re.DOTALL | re.IGNORECASE,
)

# Match standalone <m:oMath ...>...</m:oMath> (inline math, after display extracted)
_OMATH_RE = re.compile(
    r'(<m:oMath\b[^>]*>.*?</m:oMath>)',
    re.DOTALL | re.IGNORECASE,
)

# Placeholder tag format — BS4 treats these as simple unknown HTML tags
_DISPLAY_PLACEHOLDER = '<omml-display data-id="{}"></omml-display>'
_INLINE_PLACEHOLDER = '<omml-inline data-id="{}"></omml-inline>'


def _extract_omml_blocks(html: str) -> tuple[str, dict[str, str], dict[str, str]]:
    """Extract OMML blocks from raw HTML and replace with placeholders.

    Returns:
        (cleaned_html, display_blocks, inline_blocks)
        where display_blocks and inline_blocks are dicts of id → original XML
    """
    display_blocks: dict[str, str] = {}
    inline_blocks: dict[str, str] = {}
    counter = 0

    def replace_display(m: re.Match) -> str:
        nonlocal counter
        block_id = str(counter)
        counter += 1
        display_blocks[block_id] = m.group(1)
        return _DISPLAY_PLACEHOLDER.format(block_id)

    def replace_inline(m: re.Match) -> str:
        nonlocal counter
        block_id = str(counter)
        counter += 1
        inline_blocks[block_id] = m.group(1)
        return _INLINE_PLACEHOLDER.format(block_id)

    # Extract display math first (oMathPara contains oMath)
    html = _OMATHPARA_RE.sub(replace_display, html)
    # Then extract remaining standalone inline math
    html = _OMATH_RE.sub(replace_inline, html)

    return html, display_blocks, inline_blocks


def _detect_math_env_from_xml(xml: str) -> str:
    """Detect special math environment from raw OMML XML string."""
    xml_lower = xml.lower()
    if "<m:eqarr" in xml_lower:
        return "aligned"
    # Multiple <m:oMath> inside one <m:oMathPara> = multi-line display
    omath_count = len(re.findall(r'<m:oMath\b', xml, re.IGNORECASE))
    if omath_count > 1:
        return "multiline"
    if re.search(r'<m:m\b', xml_lower):
        return "pmatrix"
    return ""


# ---------------------------------------------------------------------------
# Main parse function
# ---------------------------------------------------------------------------

def _preserve_spacerun_indent(html: str) -> str:
    """Replace spaces inside mso-spacerun:yes spans with _INDENT_MARKER.

    lxml's HTML parser may collapse or reorder whitespace inside inline
    elements, losing the indentation that Word encodes in these spans.
    By swapping each space for a non-whitespace marker *before* parsing,
    the count survives through BS4 into _extract_code_line_text.
    Newlines inside the span (HTML source formatting) are simply dropped.
    """
    def replace(m: re.Match) -> str:
        spaces = m.group(2).count(' ')
        return m.group(1) + (_INDENT_MARKER * spaces) + m.group(3)

    return _SPACERUN_RE.sub(replace, html)


def parse_clipboard_html(html: str) -> list[DocNode]:
    """Parse Word clipboard HTML into a list of DocNode objects."""
    # Step 1: Unwrap OMML from conditional comments
    html = _unwrap_omml_conditionals(html)

    # Step 2: Extract OMML blocks BEFORE BS4 can mangle them.
    # BS4's lxml parser lowercases tags, restructures self-closing tags,
    # and reorders attributes — all of which break Pandoc's XML parsing.
    html, display_blocks, inline_blocks = _extract_omml_blocks(html)

    # Step 2b: Preserve mso-spacerun indentation before lxml can collapse it.
    html = _preserve_spacerun_indent(html)

    # Step 3: Now let BS4 parse the cleaned HTML (no OMML, just placeholders)
    soup = BeautifulSoup(html, "lxml")
    body = soup.body or soup

    nodes: list[DocNode] = []
    _walk_elements(body, nodes, display_blocks, inline_blocks)
    nodes = _group_code_lines(nodes)
    return nodes


# ---------------------------------------------------------------------------
# Tree walking
# ---------------------------------------------------------------------------

def _walk_elements(
    parent: Tag,
    nodes: list[DocNode],
    display_blocks: dict[str, str],
    inline_blocks: dict[str, str],
) -> None:
    """Recursively walk HTML elements and build DocNode list."""
    for child in parent.children:
        if isinstance(child, NavigableString):
            text = _normalize_text(str(child))
            if text and text not in ("StartFragment", "EndFragment"):
                nodes.append(DocNode(type=NodeType.TEXT, content=text, html=text))
            continue

        if not isinstance(child, Tag):
            continue

        tag_name = child.name.lower() if child.name else ""

        # Check for our OMML placeholders
        if tag_name == "omml-display":
            block_id = child.get("data-id", "")
            xml = display_blocks.get(block_id, "")
            if xml:
                math_env = _detect_math_env_from_xml(xml)
                nodes.append(DocNode(
                    type=NodeType.DISPLAY_MATH,
                    omml_xml=xml,
                    math_env=math_env,
                ))
            continue

        if tag_name == "omml-inline":
            block_id = child.get("data-id", "")
            xml = inline_blocks.get(block_id, "")
            if xml:
                nodes.append(DocNode(
                    type=NodeType.INLINE_MATH,
                    omml_xml=xml,
                ))
            continue

        # Check for tables
        if tag_name == "table":
            _handle_table(child, nodes, display_blocks, inline_blocks)
            continue

        # Check for list elements
        if tag_name in ("ul", "ol"):
            _handle_list(child, nodes)
            continue

        # Handle <pre> elements as fenced code blocks
        if tag_name == "pre":
            code = child.get_text().strip('\n\r')
            if code:
                nodes.append(DocNode(type=NodeType.TEXT, content=f"```\n{code}\n```", html=""))
            continue

        # Check for paragraphs
        if tag_name == "p":
            _handle_paragraph(child, nodes, display_blocks, inline_blocks)
            continue

        # Check for headings (h1-h6 or Word's MsoHeading class)
        heading_level = _detect_heading(child)
        if heading_level:
            text = child.get_text(strip=True)
            nodes.append(DocNode(type=NodeType.HEADING, content=text, level=heading_level))
            continue

        # Check for w:p (Word paragraph) tags — these appear when parsing raw OOXML
        if tag_name in ("w:p",):
            _handle_word_paragraph(child, nodes, display_blocks, inline_blocks)
            continue

        # Recurse into other elements (div, span, body, etc.)
        _walk_elements(child, nodes, display_blocks, inline_blocks)


def _detect_heading(tag: Tag) -> int | None:
    """Detect heading level from tag name or Word CSS class."""
    name = tag.name.lower() if tag.name else ""
    if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        return int(name[1])

    cls = tag.get("class", [])
    if isinstance(cls, str):
        cls = cls.split()
    for c in cls:
        m = HEADING_RE.match(c)
        if m:
            return int(m.group(1))
    return None


def _get_list_level(p_tag: Tag) -> int | None:
    """Return the mso-list nesting level (1-based) if this is a Word list item, else None."""
    style = p_tag.get("style", "")
    m = re.search(r'mso-list\s*:[^;]*level(\d+)', style, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # Fallback: MsoListParagraph* classes without explicit mso-list style
    cls = p_tag.get("class", [])
    if isinstance(cls, str):
        cls = cls.split()
    for c in cls:
        if re.match(r'msolistparagraph', c, re.IGNORECASE):
            return 1
    return None


def _handle_paragraph(
    p_tag: Tag,
    nodes: list[DocNode],
    display_blocks: dict[str, str],
    inline_blocks: dict[str, str],
) -> None:
    """Process a <p> that may contain mixed text and inline math placeholders."""
    # Check if the paragraph contains a display math placeholder
    display_placeholder = p_tag.find("omml-display")
    if display_placeholder:
        block_id = display_placeholder.get("data-id", "")
        xml = display_blocks.get(block_id, "")
        if xml:
            math_env = _detect_math_env_from_xml(xml)
            nodes.append(DocNode(
                type=NodeType.DISPLAY_MATH,
                omml_xml=xml,
                math_env=math_env,
            ))
        return

    # Check heading via class
    heading_level = _detect_heading(p_tag)
    if heading_level:
        text = p_tag.get_text(strip=True)
        nodes.append(DocNode(type=NodeType.HEADING, content=text, level=heading_level))
        return

    # Detect Word list-item paragraphs (mso-list style) before code detection.
    list_level = _get_list_level(p_tag)
    if list_level is not None:
        _handle_list_item_para(p_tag, nodes, list_level, inline_blocks)
        return

    # Detect monospace/code paragraphs (e.g. Courier New from Word/Slack).
    if _is_monospace_paragraph(p_tag):
        text = _extract_code_line_text(p_tag)
        if text.strip():
            nodes.append(DocNode(type=NodeType.CODE_LINE, content=text))
        return

    # Build paragraph with inline children
    para_children: list[DocNode] = []
    _extract_inline(p_tag, para_children, inline_blocks)

    if para_children:
        if len(para_children) == 1:
            nodes.append(para_children[0])
        else:
            nodes.append(DocNode(
                type=NodeType.PARAGRAPH,
                children=para_children,
                html=str(p_tag),
            ))


def _handle_word_paragraph(
    wp_tag: Tag,
    nodes: list[DocNode],
    display_blocks: dict[str, str],
    inline_blocks: dict[str, str],
) -> None:
    """Process a <w:p> Word paragraph (from raw OOXML)."""
    # Check for display math placeholder inside
    display_placeholder = wp_tag.find("omml-display")
    if display_placeholder:
        block_id = display_placeholder.get("data-id", "")
        xml = display_blocks.get(block_id, "")
        if xml:
            math_env = _detect_math_env_from_xml(xml)
            nodes.append(DocNode(
                type=NodeType.DISPLAY_MATH,
                omml_xml=xml,
                math_env=math_env,
            ))
        return

    # Extract text from <w:t> tags and inline math placeholders
    para_children: list[DocNode] = []
    for wt in wp_tag.find_all(["w:t", "omml-inline"]):
        tag_name = wt.name.lower() if wt.name else ""
        if tag_name == "omml-inline":
            block_id = wt.get("data-id", "")
            xml = inline_blocks.get(block_id, "")
            if xml:
                para_children.append(DocNode(
                    type=NodeType.INLINE_MATH,
                    omml_xml=xml,
                ))
        elif tag_name == "w:t":
            text = wt.get_text()
            if text.strip():
                para_children.append(DocNode(type=NodeType.TEXT, content=text, html=text))

    if para_children:
        if len(para_children) == 1:
            nodes.append(para_children[0])
        else:
            nodes.append(DocNode(
                type=NodeType.PARAGRAPH,
                children=para_children,
            ))


def _handle_list_item_para(
    p_tag: Tag,
    nodes: list[DocNode],
    level: int,
    inline_blocks: dict[str, str],
) -> None:
    """Convert a Word mso-list paragraph into a Markdown list-item TEXT node.

    Word flattens lists into consecutive <p> elements with ``mso-list:lN levelM``
    styles rather than <ul>/<ol><li>.  The bullet glyph lives in a Symbol-font
    or mso-spacerun span that we discard; the actual text follows.

    Output format:  ``  - text`` (two spaces per nesting level beyond 1).
    """
    text_parts: list[str] = []
    for child in p_tag.descendants:
        if not isinstance(child, NavigableString):
            continue
        # Skip text inside Symbol-font spans (bullet glyphs like ·, o, §)
        parent = child.parent
        if isinstance(parent, Tag):
            pstyle = parent.get("style", "").lower()
            if "font-family:symbol" in pstyle.replace(" ", ""):
                continue
            # Skip mso-spacerun spans (just list indentation noise)
            if "mso-spacerun" in pstyle:
                continue
        text = str(child).replace(_INDENT_MARKER, "").strip()
        if text:
            text_parts.append(text)

    text = " ".join(text_parts).strip()
    # Strip leading bullet characters that survived (·, •, o, §, etc.)
    text = re.sub(r'^[·•◦▪▫○●◉◌▸▹▶▷‣⁃§o]\s*', '', text)
    if not text:
        return

    indent = "  " * (level - 1)
    nodes.append(DocNode(type=NodeType.TEXT, content=f"{indent}- {text}", html=""))


def _is_monospace_paragraph(p_tag: Tag) -> bool:
    """Return True if the *entire* paragraph is code/monospace content.

    Signals checked:
    1. All non-whitespace text content lives inside monospace font spans.
    2. A ``mso-spacerun:yes`` span with only _INDENT_MARKERs is present
       alongside monospace content (indentation markers for code).

    A paragraph where monospace spans are mixed with regular text (inline code
    inside a sentence) returns False so that ``_extract_inline`` can detect
    individual backtick spans instead.

    Word list-item paragraphs (mso-list style) are always excluded.
    """
    # Exclude Word list item paragraphs — they use mso-list in their style.
    p_style = p_tag.get("style", "").lower()
    if "mso-list" in p_style:
        return False
    p_class = " ".join(
        p_tag.get("class", [])
        if isinstance(p_tag.get("class", []), list)
        else p_tag.get("class", "").split()
    )
    if re.search(r'mso\w*list', p_class, re.IGNORECASE):
        return False

    has_monospace_text = False
    has_non_monospace_text = False
    has_spacerun_indent = False

    for child in p_tag.children:
        if isinstance(child, NavigableString):
            # Bare text node directly inside <p> — non-monospace
            if str(child).replace(_INDENT_MARKER, "").strip():
                has_non_monospace_text = True
            continue
        if not isinstance(child, Tag):
            continue
        style = child.get("style", "").lower()

        # mso-spacerun indent span
        if "mso-spacerun" in style:
            text = child.get_text()
            cleaned = text.replace(_INDENT_MARKER, "").strip()
            if text and not cleaned:
                has_spacerun_indent = True
            continue

        # Skip Word field / annotation tags that carry no visible text
        if child.name and child.name.lower() in ("o:p", "w:bookmarkstart", "w:bookmarkend"):
            continue

        # Check if this direct child span has a monospace font
        is_mono = "font-family" in style and any(f in style for f in _MONOSPACE_FONTS)
        child_text = child.get_text().replace(_INDENT_MARKER, "").strip()
        if not child_text:
            continue
        if is_mono:
            has_monospace_text = True
        else:
            has_non_monospace_text = True

    if has_non_monospace_text:
        return False  # Mixed content — use inline backtick detection instead
    return has_monospace_text or has_spacerun_indent


def _extract_code_line_text(p_tag: Tag) -> str:
    """Extract one line of code text from a monospace paragraph.

    Before BS4 parsing, _preserve_spacerun_indent replaced each space in
    mso-spacerun:yes spans with _INDENT_MARKER (\\x01).  Here we count leading
    markers as the indentation depth (converting back to spaces), then collapse
    any remaining internal whitespace in the content.

    lxml's HTML parser may insert whitespace (spaces/tabs) between tags as
    source-formatting noise, so we strip those before counting the markers.
    """
    raw = p_tag.get_text().strip("\n\r")  # drop surrounding HTML newlines
    if not raw.strip(_INDENT_MARKER).strip():
        return ''
    # Strip HTML-source spaces/tabs that precede the indent markers so they
    # don't prevent lstrip(_INDENT_MARKER) from finding the real indentation.
    trimmed = raw.lstrip(' \t')
    inner = trimmed.lstrip(_INDENT_MARKER)
    leading = len(trimmed) - len(inner)
    # Collapse remaining internal whitespace in the content
    content = re.sub(r'\s+', ' ', inner.lstrip()).strip()
    return ' ' * leading + content


def _group_code_lines(nodes: list[DocNode]) -> list[DocNode]:
    """Merge consecutive CODE_LINE nodes into fenced code blocks.

    Word/Slack clipboard HTML often contains the same JSON/code twice: once in
    the default document font (plain MsoNormal) and once in Courier New.  This
    produces two code blocks whose stripped line-sets have a subset relationship
    (the plain block is missing the outer braces that became TEXT nodes).

    Strategy:
    - Build entries: ('code', lines) or ('node', DocNode).
    - For each code block whose stripped lines are a *subset* of a later code
      block's stripped lines, mark that earlier block for removal.
    - Also mark any surrounding TEXT nodes whose stripped content appears as a
      line in the later (superset) block — they are the "orphaned" outer lines
      (e.g. ``"metadata": {`` and ``},``) that belong to the duplicate.
    """
    # First pass: group consecutive CODE_LINE runs.
    entries: list[tuple] = []
    i = 0
    while i < len(nodes):
        if nodes[i].type == NodeType.CODE_LINE:
            lines: list[str] = []
            while i < len(nodes) and nodes[i].type == NodeType.CODE_LINE:
                lines.append(nodes[i].content)
                i += 1
            entries.append(('code', lines))
        else:
            entries.append(('node', nodes[i]))
            i += 1

    # Second pass: subset-based deduplication.
    # Build (index, stripped_key) pairs for all code blocks.
    code_entries = [
        (idx, frozenset(ln.strip() for ln in e[1] if ln.strip()))
        for idx, e in enumerate(entries)
        if e[0] == 'code'
    ]

    to_remove: set[int] = set()
    for ci, (idx_i, key_i) in enumerate(code_entries):
        if not key_i:
            continue
        for idx_j, key_j in code_entries[ci + 1:]:
            if key_i <= key_j:  # block i is a subset of block j → duplicate
                to_remove.add(idx_i)
                # Also remove TEXT nodes before block j whose content is a
                # line in block j (the orphaned outer lines of the duplicate).
                for k in range(idx_j):
                    if k == idx_i or k in to_remove:
                        continue
                    e = entries[k]
                    if e[0] == 'node' and e[1].content.strip() in key_j:
                        to_remove.add(k)
                break

    # Build final list.
    result: list[DocNode] = []
    for idx, entry in enumerate(entries):
        if idx in to_remove:
            continue
        if entry[0] == 'code':
            code = "\n".join(entry[1])
            result.append(DocNode(type=NodeType.TEXT, content=f"```\n{code}\n```", html=""))
        else:
            result.append(entry[1])
    return result


def _normalize_text(text: str) -> str:
    """Normalize whitespace while preserving meaningful leading indentation.

    Surrounding newlines/carriage-returns are HTML source formatting noise and
    are stripped first.  Any leading spaces that remain after that strip are
    treated as intentional indentation (e.g. inside a code block) and kept.
    Internal runs of spaces/tabs are collapsed to a single space.
    """
    # Remove surrounding newlines (HTML tag-formatting noise)
    text = text.strip('\n\r')
    if not text.strip():
        return ''

    # Count remaining leading spaces/tabs (meaningful indentation)
    stripped = text.lstrip(' \t')
    leading_ws = text[:len(text) - len(stripped)]
    leading_spaces = leading_ws.replace('\t', '    ')

    # Collapse ALL internal whitespace (including newlines) to single spaces.
    # _INDENT_MARKER (\ue000) is NOT whitespace so re.sub leaves it untouched;
    # convert it back to a real space AFTER collapsing so that runs of markers
    # (from mso-spacerun spans) are preserved as-is rather than merged.
    content = re.sub(r'\s+', ' ', stripped).strip()
    return (leading_spaces + content).replace(_INDENT_MARKER, ' ')


def _span_is_monospace(span: Tag) -> bool:
    """Return True if a <span> uses a monospace font (inline code candidate)."""
    style = span.get("style", "").lower()
    if "font-family" not in style:
        return False
    return any(font in style for font in _MONOSPACE_FONTS)


def _extract_inline(
    parent: Tag,
    out: list[DocNode],
    inline_blocks: dict[str, str],
) -> None:
    """Extract inline text and math placeholder nodes from a parent element."""
    for child in parent.children:
        if isinstance(child, NavigableString):
            text = _normalize_text(str(child))
            if text:
                out.append(DocNode(type=NodeType.TEXT, content=text, html=text))
            continue

        if not isinstance(child, Tag):
            continue

        tag_name = child.name.lower() if child.name else ""

        if tag_name == "omml-inline":
            block_id = child.get("data-id", "")
            xml = inline_blocks.get(block_id, "")
            if xml:
                out.append(DocNode(type=NodeType.INLINE_MATH, omml_xml=xml))
        elif tag_name in _FORMATTING_TAGS:
            text = child.get_text()
            if text.strip():
                out.append(DocNode(type=NodeType.TEXT, content=text, html=str(child)))
        elif tag_name == "span" and _span_is_monospace(child):
            # Inline monospace span inside a normal paragraph → backtick code.
            # Use html="" so node_to_markdown returns content directly (no
            # re-parsing through html_to_markdown which doesn't know <code>).
            text = child.get_text().strip()
            if text:
                out.append(DocNode(type=NodeType.TEXT, content=f"`{text}`", html=""))
        else:
            # Recurse into other container elements (span, div, etc.)
            inner_nodes: list[DocNode] = []
            _extract_inline(child, inner_nodes, inline_blocks)
            if inner_nodes:
                out.extend(inner_nodes)
            else:
                text = child.get_text()
                if text.strip():
                    out.append(DocNode(type=NodeType.TEXT, content=text, html=str(child)))


def _handle_list(list_tag: Tag, nodes: list[DocNode]) -> None:
    """Convert a <ul>/<ol> element (with optional nested lists) to a TEXT node
    containing Markdown list syntax.  Nesting is rendered with 2-space indent
    per level so that renderers produce proper sub-lists.
    """
    lines = _list_to_md_lines(list_tag, depth=0)
    if lines:
        nodes.append(DocNode(type=NodeType.TEXT, content="\n".join(lines), html=""))


def _list_to_md_lines(list_tag: Tag, depth: int) -> list[str]:
    """Recursively convert a <ul>/<ol> to Markdown list lines.

    Handles two structures:
    - Standard: <ul><li>text<ul><li>sub</li></ul></li></ul>
    - Word quirk: <ul><li>text</li><ul><li>sub</li></ul></ul>
      (nested <ul> is a sibling of <li>, not inside it)
    """
    ordered = list_tag.name.lower() == "ol" if list_tag.name else False
    lines: list[str] = []
    idx = 1
    indent = "  " * depth

    for child in list_tag.children:
        if not isinstance(child, Tag) or not child.name:
            continue
        child_name = child.name.lower()

        if child_name == "li":
            # Separate direct text/inline content from nested lists
            item_parts: list[str] = []
            nested: list[Tag] = []
            for node in child.children:
                if isinstance(node, NavigableString):
                    t = str(node).strip()
                    if t:
                        item_parts.append(t)
                elif isinstance(node, Tag) and node.name and node.name.lower() in ("ul", "ol"):
                    nested.append(node)
                else:
                    t = node.get_text()
                    if t.strip():
                        item_parts.append(t)

            # Collapse HTML source line-breaks and extra whitespace within item text
            item_text = re.sub(r'\s+', ' ', " ".join(item_parts)).strip()
            prefix = f"{idx}." if ordered else "-"
            idx += 1
            lines.append(f"{indent}{prefix} {item_text}")

            for sub_list in nested:
                lines.extend(_list_to_md_lines(sub_list, depth + 1))

        elif child_name in ("ul", "ol"):
            # Word HTML quirk: nested list appears as direct child of outer list
            # (sibling of <li> rather than inside one). Attach at next depth.
            lines.extend(_list_to_md_lines(child, depth + 1))

    return lines


def _handle_table(
    table_tag: Tag,
    nodes: list[DocNode],
    display_blocks: dict[str, str],
    inline_blocks: dict[str, str],
) -> None:
    """Process a <table> element into a TABLE DocNode."""
    rows: list[list[list[DocNode]]] = []

    for tr in table_tag.find_all("tr"):
        row_cells: list[list[DocNode]] = []
        for cell in tr.find_all(["td", "th"]):
            cell_nodes: list[DocNode] = []
            _extract_cell_content(cell, cell_nodes, display_blocks, inline_blocks)
            row_cells.append(cell_nodes)
        if row_cells:
            rows.append(row_cells)

    if rows:
        nodes.append(DocNode(type=NodeType.TABLE, table_rows=rows))


def _extract_cell_content(
    cell_tag: Tag,
    out: list[DocNode],
    display_blocks: dict[str, str],
    inline_blocks: dict[str, str],
) -> None:
    """Extract content from a table cell (<td> or <th>)."""
    # Word wraps cell content in <p> tags — extract inline content from each.
    paragraphs = cell_tag.find_all("p")
    if paragraphs:
        for p in paragraphs:
            # Check for display math placeholder
            display_placeholder = p.find("omml-display")
            if display_placeholder:
                block_id = display_placeholder.get("data-id", "")
                xml = display_blocks.get(block_id, "")
                if xml:
                    math_env = _detect_math_env_from_xml(xml)
                    out.append(DocNode(
                        type=NodeType.DISPLAY_MATH,
                        omml_xml=xml,
                        math_env=math_env,
                    ))
                continue
            _extract_inline(p, out, inline_blocks)
    else:
        # No <p> wrappers — extract directly from cell
        _extract_inline(cell_tag, out, inline_blocks)
