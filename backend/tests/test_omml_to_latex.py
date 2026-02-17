"""Tests for OMML → LaTeX conversion."""

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from omml_to_latex import omml_to_latex, _strip_math_delimiters, _fallback_text_extract

FIXTURES = Path(__file__).parent / "fixtures"

# Skip all Pandoc-dependent tests if Pandoc is not installed
pytestmark = pytest.mark.skipif(
    shutil.which("pandoc") is None,
    reason="Pandoc not installed",
)


def test_inline_math_conversion():
    omml = (FIXTURES / "inline_math.xml").read_text(encoding="utf-8")
    result = omml_to_latex(omml)
    assert result  # non-empty
    assert "frac" in result or "/" in result  # should have fraction


def test_display_math_conversion():
    omml = (FIXTURES / "display_math.xml").read_text(encoding="utf-8")
    result = omml_to_latex(omml)
    assert result
    assert "sum" in result or "Σ" in result or "i" in result


def test_strip_delimiters():
    assert _strip_math_delimiters("$x+y$") == "x+y"
    assert _strip_math_delimiters("\\[x+y\\]") == "x+y"
    assert _strip_math_delimiters("\\(x+y\\)") == "x+y"
    assert _strip_math_delimiters("x+y") == "x+y"


def test_fallback_text_extract():
    xml = "<m:r><m:t>hello</m:t></m:r>"
    assert _fallback_text_extract(xml) == "hello"


def test_clipboard_omml_with_html_tags():
    """Clipboard OMML has HTML tags (<font>, <span>, <i>, <br>) mixed in."""
    omml = (FIXTURES / "clipboard_omml_with_html.xml").read_text(encoding="utf-8")
    result = omml_to_latex(omml)
    # Should produce real LaTeX, not plain text fallback
    assert "\\log" in result
    assert "m" in result
    assert "M" in result
    assert "15800" in result
