"""Clean up Word HTML for Obsidian-friendly output."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from parser import DocNode, NodeType


def clean_html(html: str) -> str:
    """Clean Word's messy HTML into minimal, semantic HTML."""
    soup = BeautifulSoup(html, "lxml")
    body = soup.body or soup

    # Remove Word-specific style attributes and classes
    for tag in body.find_all(True):
        _clean_tag(tag)

    # Get just the inner content (not <html><body> wrappers)
    return body.decode_contents().strip()


def node_to_html(node: DocNode) -> str:
    """Convert a single DocNode to clean HTML."""
    if node.type == NodeType.TEXT:
        if node.html:
            return clean_html(node.html)
        return _escape_html(node.content)

    if node.type in (NodeType.INLINE_MATH, NodeType.DISPLAY_MATH):
        return ""  # handled by converter

    if node.type == NodeType.HEADING:
        level = min(node.level, 6)
        return f"<h{level}>{_escape_html(node.content)}</h{level}>"

    if node.type == NodeType.PARAGRAPH:
        parts = []
        for child in node.children:
            parts.append(node_to_html(child))
        return f"<p>{''.join(parts)}</p>"

    if node.type == NodeType.LIST:
        tag = "ol" if node.list_ordered else "ul"
        items = []
        for child in node.children:
            items.append(f"<li>{node_to_html(child)}</li>")
        return f"<{tag}>{''.join(items)}</{tag}>"

    return _escape_html(node.content)


def _clean_tag(tag: Tag) -> None:
    """Remove Word-specific attributes from an HTML tag."""
    # Remove style attribute (Word inlines tons of CSS)
    if tag.has_attr("style"):
        del tag["style"]

    # Remove Word-specific classes but keep semantic ones
    if tag.has_attr("class"):
        classes = tag["class"]
        if isinstance(classes, str):
            classes = classes.split()
        # Remove Mso* classes
        cleaned = [c for c in classes if not c.startswith("Mso")]
        if cleaned:
            tag["class"] = cleaned
        else:
            del tag["class"]

    # Remove other Word-specific attributes
    for attr in list(tag.attrs.keys()):
        if attr.startswith("data-") or attr in ("lang", "xml:lang"):
            del tag[attr]


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
