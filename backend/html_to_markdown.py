"""Convert HTML formatting tags to Markdown."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, NavigableString, Tag

from parser import DocNode, NodeType


def html_to_markdown(html: str) -> str:
    """Convert an HTML string to Markdown."""
    soup = BeautifulSoup(html, "lxml")
    body = soup.body or soup
    return _convert_element(body).strip()


def node_to_markdown(node: DocNode) -> str:
    """Convert a single DocNode to Markdown."""
    if node.type == NodeType.TEXT:
        if node.html:
            return html_to_markdown(node.html)
        return node.content

    if node.type in (NodeType.INLINE_MATH, NodeType.DISPLAY_MATH):
        return ""  # handled by converter

    if node.type == NodeType.HEADING:
        prefix = "#" * node.level
        return f"{prefix} {node.content}"

    if node.type == NodeType.PARAGRAPH:
        parts = []
        for child in node.children:
            parts.append(node_to_markdown(child))
        return "".join(parts)

    if node.type == NodeType.LIST:
        items = []
        for i, child in enumerate(node.children):
            prefix = f"{i + 1}." if node.list_ordered else "-"
            items.append(f"{prefix} {node_to_markdown(child)}")
        return "\n".join(items)

    return node.content


def _convert_element(element: Tag | NavigableString) -> str:
    """Recursively convert an HTML element to Markdown."""
    if isinstance(element, NavigableString):
        return str(element)

    if not isinstance(element, Tag):
        return ""

    tag = element.name.lower() if element.name else ""
    inner = "".join(_convert_element(c) for c in element.children)

    if tag in ("b", "strong"):
        return f"**{inner}**"
    if tag in ("i", "em"):
        return f"*{inner}*"
    if tag == "u":
        return f"<u>{inner}</u>"
    if tag == "sup":
        return f"<sup>{inner}</sup>"
    if tag == "sub":
        return f"<sub>{inner}</sub>"
    if tag == "br":
        return "\n"
    if tag == "ul":
        items = _collect_list_items(element)
        return "\n".join(f"- {item}" for item in items)
    if tag == "ol":
        items = _collect_list_items(element)
        return "\n".join(f"{i + 1}. {item}" for i, item in enumerate(items))
    if tag == "li":
        return inner.strip()
    if tag == "p":
        return inner + "\n\n"

    # Word heading classes
    cls = element.get("class", [])
    if isinstance(cls, str):
        cls = cls.split()
    for c in cls:
        m = re.match(r"MsoHeading(\d)", c, re.IGNORECASE)
        if m:
            level = int(m.group(1))
            prefix = "#" * level
            return f"{prefix} {inner.strip()}\n\n"

    return inner


def _collect_list_items(list_tag: Tag) -> list[str]:
    """Collect list item text from a <ul> or <ol>."""
    items = []
    for child in list_tag.children:
        if isinstance(child, Tag) and child.name and child.name.lower() == "li":
            items.append(_convert_element(child).strip())
    return items
