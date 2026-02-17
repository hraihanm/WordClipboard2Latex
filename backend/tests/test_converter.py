"""Tests for the converter orchestrator."""

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from converter import convert_html

FIXTURES = Path(__file__).parent / "fixtures"


def test_convert_empty_html():
    result = convert_html("")
    assert result["latex"] == ""
    assert result["markdown"] == ""
    assert result["html"] == ""
    assert len(result["warnings"]) > 0


def test_convert_plain_text():
    html = "<html><body><p>Hello world</p></body></html>"
    result = convert_html(html)
    assert "Hello" in result["latex"] or "Hello" in result["markdown"]


def test_convert_heading():
    html = '<html><body><p class="MsoHeading1">My Title</p></body></html>'
    result = convert_html(html)
    assert "\\section{" in result["latex"] or "My Title" in result["latex"]
    assert "# My Title" in result["markdown"]


def test_convert_bold_italic():
    html = "<html><body><p><b>bold</b> and <i>italic</i></p></body></html>"
    result = convert_html(html)
    assert "\\textbf{bold}" in result["latex"]
    assert "\\textit{italic}" in result["latex"]
    assert "**bold**" in result["markdown"]
    assert "*italic*" in result["markdown"]


@pytest.mark.skipif(
    shutil.which("pandoc") is None,
    reason="Pandoc not installed",
)
def test_convert_full_document():
    html = (FIXTURES / "word_clipboard.html").read_text(encoding="utf-8")
    result = convert_html(html)
    assert result["latex"]
    assert result["markdown"]
    assert result["html"]
    # Should have section heading
    assert "\\section{" in result["latex"] or "Introduction" in result["latex"]


@pytest.mark.skipif(
    shutil.which("pandoc") is None,
    reason="Pandoc not installed",
)
def test_convert_conditional_comments():
    """End-to-end: Word clipboard with OMML in conditional comments."""
    html = (FIXTURES / "word_conditional_comments.html").read_text(encoding="utf-8")
    result = convert_html(html)

    latex = result["latex"]
    md = result["markdown"]

    # Should have text content
    assert "Hitung" in latex
    assert "bintang" in latex

    # Should have aligned environment (the 4-line equation block)
    assert "\\begin{aligned}" in latex

    # Should have log with subscript 10
    assert "log" in latex

    # Markdown should have $...$ or $$...$$
    assert "$" in md

    print("=== LaTeX output ===")
    print(latex)
    print("=== Markdown output ===")
    print(md)


@pytest.mark.skipif(
    shutil.which("pandoc") is None,
    reason="Pandoc not installed",
)
def test_convert_real_word_document():
    """End-to-end: real Word OOXML document with multi-line display math."""
    xml = (FIXTURES / "real_word_document.xml").read_text(encoding="utf-8")
    result = convert_html(xml)

    latex = result["latex"]

    # Text content
    assert "Hitung" in latex
    assert "bintang" in latex

    # Multi-line aligned equation
    assert "\\begin{aligned}" in latex
    assert "\\log_{10}" in latex
    assert "15800" in latex

    # Fraction should be intact (not split by multiline)
    assert "\\frac{L}{L_{\\star}}" in latex

    # Inline math
    assert "$N$" in latex


def test_response_shape():
    result = convert_html("<html><body><p>test</p></body></html>")
    assert "latex" in result
    assert "markdown" in result
    assert "html" in result
    assert "warnings" in result
    assert isinstance(result["warnings"], list)
