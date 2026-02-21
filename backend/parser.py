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

def parse_clipboard_html(html: str) -> list[DocNode]:
    """Parse Word clipboard HTML into a list of DocNode objects."""
    # Step 1: Unwrap OMML from conditional comments
    html = _unwrap_omml_conditionals(html)

    # Step 2: Extract OMML blocks BEFORE BS4 can mangle them.
    # BS4's lxml parser lowercases tags, restructures self-closing tags,
    # and reorders attributes — all of which break Pandoc's XML parsing.
    html, display_blocks, inline_blocks = _extract_omml_blocks(html)

    # Step 3: Now let BS4 parse the cleaned HTML (no OMML, just placeholders)
    soup = BeautifulSoup(html, "lxml")
    body = soup.body or soup

    nodes: list[DocNode] = []
    _walk_elements(body, nodes, display_blocks, inline_blocks)
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


def _normalize_text(text: str) -> str:
    """Collapse internal whitespace/newlines into single spaces."""
    return re.sub(r'\s+', ' ', text).strip()


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
    """Create a list node from a <ul> or <ol> element."""
    ordered = list_tag.name.lower() == "ol" if list_tag.name else False
    children: list[DocNode] = []
    for child in list_tag.children:
        if isinstance(child, Tag) and child.name and child.name.lower() == "li":
            text = child.get_text(strip=True)
            children.append(DocNode(type=NodeType.TEXT, content=text, html=str(child)))
    nodes.append(DocNode(
        type=NodeType.LIST,
        children=children,
        list_ordered=ordered,
    ))


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
