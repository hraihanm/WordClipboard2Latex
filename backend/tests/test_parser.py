"""Tests for the HTML + OMML parser."""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from parser import DocNode, NodeType, parse_clipboard_html


FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_heading():
    html = '<html><body><p class="MsoHeading1">Introduction</p></body></html>'
    nodes = parse_clipboard_html(html)
    assert len(nodes) >= 1
    heading = next(n for n in nodes if n.type == NodeType.HEADING)
    assert heading.level == 1
    assert heading.content == "Introduction"


def test_parse_plain_text():
    html = "<html><body><p>Hello world</p></body></html>"
    nodes = parse_clipboard_html(html)
    assert len(nodes) >= 1
    text_node = nodes[0]
    assert text_node.type in (NodeType.TEXT, NodeType.PARAGRAPH)


def test_parse_inline_math():
    omml = (FIXTURES / "inline_math.xml").read_text(encoding="utf-8")
    html = f'<html xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"><body><p>Text {omml} more text</p></body></html>'
    nodes = parse_clipboard_html(html)
    math_nodes = [n for n in _flatten(nodes) if n.type == NodeType.INLINE_MATH]
    assert len(math_nodes) >= 1
    assert math_nodes[0].omml_xml  # has XML content


def test_parse_display_math():
    omml = (FIXTURES / "display_math.xml").read_text(encoding="utf-8")
    html = f'<html xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"><body>{omml}</body></html>'
    nodes = parse_clipboard_html(html)
    math_nodes = [n for n in _flatten(nodes) if n.type == NodeType.DISPLAY_MATH]
    assert len(math_nodes) >= 1


def test_parse_aligned_detected():
    omml = (FIXTURES / "aligned_math.xml").read_text(encoding="utf-8")
    html = f'<html xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"><body>{omml}</body></html>'
    nodes = parse_clipboard_html(html)
    math_nodes = [n for n in _flatten(nodes) if n.type == NodeType.DISPLAY_MATH]
    assert len(math_nodes) >= 1
    assert math_nodes[0].math_env == "aligned"


def test_parse_full_document():
    html = (FIXTURES / "word_clipboard.html").read_text(encoding="utf-8")
    nodes = parse_clipboard_html(html)
    assert len(nodes) >= 3  # heading + paragraphs + math + list

    types = {n.type for n in _flatten(nodes)}
    assert NodeType.HEADING in types


def test_parse_conditional_comments():
    """Test that OMML inside Word conditional comments is extracted."""
    html = (FIXTURES / "word_conditional_comments.html").read_text(encoding="utf-8")
    nodes = parse_clipboard_html(html)
    flat = _flatten(nodes)

    # Should find display math (the aligned equation block and the M-M* equation)
    display_nodes = [n for n in flat if n.type == NodeType.DISPLAY_MATH]
    assert len(display_nodes) >= 2, f"Expected >=2 display math nodes, got {len(display_nodes)}"

    # The first display math should be aligned (eqArr)
    assert display_nodes[0].math_env == "aligned"

    # Should find inline math (N)
    inline_nodes = [n for n in flat if n.type == NodeType.INLINE_MATH]
    assert len(inline_nodes) >= 1, f"Expected >=1 inline math nodes, got {len(inline_nodes)}"

    # Should find text nodes too
    text_nodes = [n for n in flat if n.type == NodeType.TEXT]
    assert any("Hitung" in n.content for n in text_nodes)
    assert any("bintang" in n.content for n in text_nodes)


def _flatten(nodes: list[DocNode]) -> list[DocNode]:
    """Flatten nested node tree."""
    result = []
    for n in nodes:
        result.append(n)
        if n.children:
            result.extend(_flatten(n.children))
    return result
