"""Convert HTML formatting tags to LaTeX commands."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, NavigableString, Tag

from parser import DocNode, NodeType


def html_to_latex(html: str) -> str:
    """Convert an HTML string with formatting to LaTeX."""
    soup = BeautifulSoup(html, "lxml")
    body = soup.body or soup
    return _convert_element(body).strip()


def node_to_latex(node: DocNode) -> str:
    """Convert a single DocNode to LaTeX."""
    if node.type == NodeType.TEXT:
        if node.html:
            return html_to_latex(node.html)
        return _escape_latex(node.content)

    if node.type == NodeType.INLINE_MATH:
        return ""  # handled by converter with actual LaTeX math

    if node.type == NodeType.DISPLAY_MATH:
        return ""  # handled by converter with actual LaTeX math

    if node.type == NodeType.HEADING:
        cmd = _heading_command(node.level)
        return f"\\{cmd}{{{_escape_latex(node.content)}}}"

    if node.type == NodeType.PARAGRAPH:
        parts = []
        for child in node.children:
            parts.append(node_to_latex(child))
        return "".join(parts)

    if node.type == NodeType.LIST:
        env = "enumerate" if node.list_ordered else "itemize"
        items = []
        for child in node.children:
            items.append(f"  \\item {node_to_latex(child)}")
        return f"\\begin{{{env}}}\n" + "\n".join(items) + f"\n\\end{{{env}}}"

    if node.type == NodeType.TABLE:
        return ""  # handled by converter._convert_table

    return node.content


def _heading_command(level: int) -> str:
    commands = {
        1: "section",
        2: "subsection",
        3: "subsubsection",
        4: "paragraph",
        5: "subparagraph",
        6: "subparagraph",
    }
    return commands.get(level, "section")


def _convert_element(element: Tag | NavigableString) -> str:
    """Recursively convert an HTML element to LaTeX."""
    if isinstance(element, NavigableString):
        return _escape_latex(str(element))

    if not isinstance(element, Tag):
        return ""

    tag = element.name.lower() if element.name else ""
    inner = "".join(_convert_element(c) for c in element.children)

    if tag in ("b", "strong"):
        return f"\\textbf{{{inner}}}"
    if tag in ("i", "em"):
        return f"\\textit{{{inner}}}"
    if tag == "u":
        return f"\\underline{{{inner}}}"
    if tag == "sup":
        return f"\\textsuperscript{{{inner}}}"
    if tag == "sub":
        return f"\\textsubscript{{{inner}}}"
    if tag == "br":
        return " \\\\\n"
    if tag == "ul":
        items = _collect_list_items(element)
        item_strs = [f"  \\item {item}" for item in items]
        return f"\\begin{{itemize}}\n" + "\n".join(item_strs) + "\n\\end{itemize}"
    if tag == "ol":
        items = _collect_list_items(element)
        item_strs = [f"  \\item {item}" for item in items]
        return f"\\begin{{enumerate}}\n" + "\n".join(item_strs) + "\n\\end{enumerate}"
    if tag == "li":
        return inner
    if tag == "p":
        return inner + "\n\n"

    # Check for Word heading class
    cls = element.get("class", [])
    if isinstance(cls, str):
        cls = cls.split()
    for c in cls:
        m = re.match(r"MsoHeading(\d)", c, re.IGNORECASE)
        if m:
            level = int(m.group(1))
            cmd = _heading_command(level)
            return f"\\{cmd}{{{inner.strip()}}}\n\n"

    return inner


def _collect_list_items(list_tag: Tag) -> list[str]:
    """Collect list item contents from a <ul> or <ol>."""
    items = []
    for child in list_tag.children:
        if isinstance(child, Tag) and child.name and child.name.lower() == "li":
            items.append(_convert_element(child).strip())
    return items


def _escape_latex(text: str) -> str:
    """Escape special LaTeX characters in plain text."""
    replacements = [
        ("\\", "\\textbackslash{}"),
        ("&", "\\&"),
        ("%", "\\%"),
        ("$", "\\$"),
        ("#", "\\#"),
        ("_", "\\_"),
        ("{", "\\{"),
        ("}", "\\}"),
        ("~", "\\textasciitilde{}"),
        ("^", "\\textasciicircum{}"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text
