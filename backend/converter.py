"""Orchestrator: clipboard → parsed document → LaTeX / Markdown / HTML output."""

from __future__ import annotations

import re

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

    if node.type == NodeType.TABLE:
        _convert_table(node, latex_parts, md_parts, html_parts, warnings)
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


def _convert_cell(children: list[DocNode], warnings: list[str]) -> tuple[str, str, str]:
    """Convert a table cell's children to (latex, markdown, html) strings.

    Forces all math to inline $...$ and collapses to a single line,
    because Markdown pipe tables require each row on one line.
    """
    cell_latex: list[str] = []
    cell_md: list[str] = []
    cell_html: list[str] = []

    for child in children:
        if child.type in (NodeType.INLINE_MATH, NodeType.DISPLAY_MATH):
            # Force inline math in table cells (no $$...$$ with newlines)
            latex_math = _convert_math(child, warnings).strip()
            if latex_math:
                cell_latex.append(f"${latex_math}$")
                cell_md.append(f"${latex_math}$")
                cell_html.append(f'<span class="math inline">\\({latex_math}\\)</span>')
        else:
            _convert_node(child, cell_latex, cell_md, cell_html, warnings)

    # Collapse to single line (required for Markdown pipe tables)
    def to_line(parts: list[str]) -> str:
        return re.sub(r'\s+', ' ', ' '.join(p for p in parts if p.strip())).strip()

    return to_line(cell_latex), to_line(cell_md), to_line(cell_html)


def _convert_table(
    node: DocNode,
    latex_parts: list[str],
    md_parts: list[str],
    html_parts: list[str],
    warnings: list[str],
) -> None:
    """Convert a TABLE DocNode to all three output formats."""
    latex_rows: list[list[str]] = []
    md_rows: list[list[str]] = []
    html_rows: list[list[str]] = []

    for row in node.table_rows:
        lat_cells, md_cells, htm_cells = [], [], []
        for cell_children in row:
            lat, md, htm = _convert_cell(cell_children, warnings)
            lat_cells.append(lat)
            md_cells.append(md)
            htm_cells.append(htm)
        latex_rows.append(lat_cells)
        md_rows.append(md_cells)
        html_rows.append(htm_cells)

    if not latex_rows:
        return

    num_cols = max(len(r) for r in latex_rows)

    # --- LaTeX: tabular environment ---
    col_spec = "|" + "|".join(["l"] * num_cols) + "|"
    lines = [f"\\begin{{tabular}}{{{col_spec}}}", "\\hline"]
    for row in latex_rows:
        while len(row) < num_cols:
            row.append("")
        lines.append(" & ".join(row) + " \\\\")
        lines.append("\\hline")
    lines.append("\\end{tabular}")
    latex_parts.append("\n".join(lines))

    # --- Markdown: pipe table ---
    md_lines = []
    for i, row in enumerate(md_rows):
        while len(row) < num_cols:
            row.append("")
        # Escape pipe characters inside cell content
        escaped = [c.replace("|", "\\|") for c in row]
        md_lines.append("| " + " | ".join(escaped) + " |")
        if i == 0:
            md_lines.append("| " + " | ".join(["---"] * num_cols) + " |")
    md_parts.append("\n".join(md_lines))

    # --- HTML: clean table ---
    htm_lines = ["<table>"]
    for i, row in enumerate(html_rows):
        htm_lines.append("<tr>")
        tag = "th" if i == 0 else "td"
        for cell in row:
            htm_lines.append(f"  <{tag}>{cell}</{tag}>")
        htm_lines.append("</tr>")
    htm_lines.append("</table>")
    html_parts.append("\n".join(htm_lines))
