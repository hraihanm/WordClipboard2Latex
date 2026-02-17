"""Orchestrator: clipboard → parsed document → LaTeX / Markdown / HTML output."""

from __future__ import annotations

from clipboard import read_clipboard_html
from html_to_html import node_to_html
from html_to_latex import node_to_latex, _escape_latex
from html_to_markdown import node_to_markdown
from omml_to_latex import omml_to_latex
from parser import DocNode, NodeType, parse_clipboard_html
from postprocess import postprocess_latex


def convert_clipboard() -> dict:
    """Read the Windows clipboard and convert to all output formats."""
    html = read_clipboard_html()
    if not html:
        return {
            "latex": "",
            "markdown": "",
            "html": "",
            "warnings": ["Clipboard is empty or does not contain HTML data."],
        }
    return convert_html(html)


def convert_html(html: str) -> dict:
    """Convert raw HTML (with possible OMML) to all output formats."""
    nodes = parse_clipboard_html(html)

    if not nodes:
        return {
            "latex": "",
            "markdown": "",
            "html": "",
            "warnings": ["No content found in clipboard HTML."],
        }

    warnings: list[str] = []
    latex_parts: list[str] = []
    md_parts: list[str] = []
    html_parts: list[str] = []

    for node in nodes:
        _convert_node(node, latex_parts, md_parts, html_parts, warnings)

    return {
        "latex": "\n\n".join(p for p in latex_parts if p.strip()).strip(),
        "markdown": "\n\n".join(p for p in md_parts if p.strip()).strip(),
        "html": "\n".join(p for p in html_parts if p.strip()).strip(),
        "warnings": warnings,
    }


def _convert_node(
    node: DocNode,
    latex_parts: list[str],
    md_parts: list[str],
    html_parts: list[str],
    warnings: list[str],
) -> None:
    """Convert a single DocNode and append results to the output lists."""

    if node.type == NodeType.INLINE_MATH:
        latex_math = _convert_math(node, warnings)
        latex_parts.append(f"${latex_math}$")
        md_parts.append(f"${latex_math}$")
        html_parts.append(f'<span class="math inline">\\({latex_math}\\)</span>')
        return

    if node.type == NodeType.DISPLAY_MATH:
        latex_math = _convert_math(node, warnings)
        if node.math_env in ("aligned", "multiline"):
            latex_block = f"\\[\n\\begin{{aligned}}\n{latex_math}\n\\end{{aligned}}\n\\]"
            md_block = f"$$\n\\begin{{aligned}}\n{latex_math}\n\\end{{aligned}}\n$$"
        else:
            latex_block = f"\\[\n{latex_math}\n\\]"
            md_block = f"$$\n{latex_math}\n$$"
        latex_parts.append(latex_block)
        md_parts.append(md_block)
        html_parts.append(f'<div class="math display">\\[{latex_math}\\]</div>')
        return

    if node.type == NodeType.PARAGRAPH:
        para_latex: list[str] = []
        para_md: list[str] = []
        para_html: list[str] = []
        for child in node.children:
            _convert_node(child, para_latex, para_md, para_html, warnings)
        latex_parts.append(" ".join(p for p in para_latex if p))
        md_parts.append(" ".join(p for p in para_md if p))
        html_parts.append("<p>" + " ".join(p for p in para_html if p) + "</p>")
        return

    if node.type == NodeType.HEADING:
        latex_parts.append(node_to_latex(node))
        md_parts.append(node_to_markdown(node))
        html_parts.append(node_to_html(node))
        return

    if node.type == NodeType.LIST:
        latex_parts.append(node_to_latex(node))
        md_parts.append(node_to_markdown(node))
        html_parts.append(node_to_html(node))
        return

    # Default: text node
    latex_parts.append(node_to_latex(node))
    md_parts.append(node_to_markdown(node))
    html_parts.append(node_to_html(node))


def _convert_math(node: DocNode, warnings: list[str]) -> str:
    """Convert a math DocNode's OMML to LaTeX."""
    if not node.omml_xml:
        warnings.append("Math node has no OMML XML content.")
        return ""

    try:
        raw_latex = omml_to_latex(node.omml_xml)
        return postprocess_latex(raw_latex)
    except RuntimeError as e:
        warnings.append(str(e))
        return ""
    except Exception as e:
        warnings.append(f"Math conversion error: {e}")
        return ""
