"""Convert Markdown / LaTeX text to Word-compatible clipboard content.

Strategy
--------
We write only CF_HTML (HTML Format) to the clipboard, using Pandoc's
``--mathml`` flag.

Why not CF_RTF?
  Pandoc's RTF/OMML writer silently drops all LaTeX math-spacing commands
  (``\ ``, ``\,``, ``\;``, ``\quad``, …) because OMML has no matching
  primitive.  Any preprocessing trick (replacing ``\ `` with ``\text{ }``,
  etc.) also fails because Pandoc then strips the leading space from
  ``\text{}`` content when writing the OMML ``<m:t>`` element.

Why CF_HTML with MathML?
  Pandoc's MathML writer converts spacing commands correctly:
    ``\ ``   → ``<mspace width="0.333em"/>``
    ``\,``   → ``<mspace width="0.167em"/>``
    ``\quad``→ ``<mspace width="1em"/>``
  Word 2016+ (and Word 365) renders pasted MathML equations natively,
  including the spacing.  Text formatting (headings, bold, italic, tables)
  comes through via standard HTML elements that Word handles well.

Math spacing pre-processing
---------------------------
Pandoc's MathML writer drops explicit spacing commands (``\ ``, ``\,``,
``\quad``, …) placed immediately before ``\text{}`` and also strips leading
spaces inside ``\text{ content}``.  Before calling Pandoc we rewrite these
patterns by merging the space as a tilde (``~``) into the ``\text{}``
argument.  In LaTeX text mode ``~`` is a non-breaking space (U+00A0), which
Pandoc emits as ``&#160;`` in MathML — not XML whitespace, so it survives
intact and Word renders it as a visible space.

CF_HTML format spec
-------------------
The clipboard HTML format (registered as "HTML Format") requires a small
ASCII header that records byte offsets into the payload:

    Version:0.9\r\n
    StartHTML:NNNNNNNNN\r\n
    EndHTML:NNNNNNNNN\r\n
    StartFragment:NNNNNNNNN\r\n
    EndFragment:NNNNNNNNN\r\n
    <html><body><!--StartFragment-->...CONTENT...<!--EndFragment--></body></html>

All offsets are UTF-8 byte positions from the very start of the blob.
"""

from __future__ import annotations

import re
import subprocess

import win32clipboard

CF_HTML_FORMAT = win32clipboard.RegisterClipboardFormat("HTML Format")

# Pandoc input format strings for each supported source format.
_PANDOC_INPUT: dict[str, str] = {
    "markdown": "markdown+tex_math_dollars+tex_math_single_backslash",
    "latex": "latex",
}


# ── Math spacing pre-processor ────────────────────────────────────────────────
#
# Pandoc's MathML writer (--mathml) drops explicit spacing commands (\ , \,
# \quad, …) placed before \text{} and also strips leading spaces inside
# \text{ content}.  The workaround is to replace the spacing with a LaTeX
# tilde (~), which in text mode becomes a non-breaking space (U+00A0).
# U+00A0 is not XML whitespace, so Pandoc and Word both preserve it faithfully.
#
#   Input:  1\ \text{AU}          →  1\text{~AU}
#   Input:  1\quad\text{m}        →  1\text{~m}
#   Input:  \text{ AU}            →  \text{~AU}

_SPACE_BEFORE_TEXT_RE = re.compile(
    r'(?:(?:\\[ ,;:>]|\\(?:quad|qquad|enspace|thinspace|medspace|thickspace))\s*)+'
    r'\\text\{([^}]*)\}'
)
_LEADING_SPACE_IN_TEXT_RE = re.compile(r'\\text\{ ')
_DISPLAY_MATH_RE = re.compile(r'\$\$(.*?)\$\$', re.DOTALL)
_INLINE_MATH_RE = re.compile(r'(?<!\$)\$(?!\$)(.*?)(?<!\$)\$(?!\$)')


def _fix_math_spacing(math: str) -> str:
    """Replace spacing commands before \\text{} with ~ inside \\text{}."""
    math = _SPACE_BEFORE_TEXT_RE.sub(
        lambda m: r'\text{~' + m.group(1).lstrip() + '}',
        math,
    )
    math = _LEADING_SPACE_IN_TEXT_RE.sub(r'\\text{~', math)
    return math


def _preprocess_math_spacing(text: str, fmt: str) -> str:
    """Apply spacing fix to all math spans in *text*."""
    if fmt == 'latex':
        return _fix_math_spacing(text)
    # Markdown: apply inside $$...$$ first, then $...$
    text = _DISPLAY_MATH_RE.sub(
        lambda m: '$$' + _fix_math_spacing(m.group(1)) + '$$', text
    )
    text = _INLINE_MATH_RE.sub(
        lambda m: '$' + _fix_math_spacing(m.group(1)) + '$', text
    )
    return text


# ── Pandoc helpers ────────────────────────────────────────────────────────────

def _pandoc(text: str, from_fmt: str, to_fmt: str, extra_args: list[str]) -> str:
    """Call Pandoc and return stdout as a string.

    Raises
    ------
    FileNotFoundError
        When Pandoc is not on PATH.
    RuntimeError
        When Pandoc exits with a non-zero return code.
    """
    cmd = ["pandoc", "-f", from_fmt, "-t", to_fmt, *extra_args]
    result = subprocess.run(
        cmd,
        input=text.encode("utf-8"),
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(stderr or f"pandoc exited with code {result.returncode}")
    return result.stdout.decode("utf-8", errors="replace")


# ── CF_HTML builder ───────────────────────────────────────────────────────────

_CF_HTML_HEADER_TEMPLATE = (
    "Version:0.9\r\n"
    "StartHTML:{sh:09d}\r\n"
    "EndHTML:{eh:09d}\r\n"
    "StartFragment:{sf:09d}\r\n"
    "EndFragment:{ef:09d}\r\n"
)

_OPEN_TAG = b"<html><body><!--StartFragment-->"
_CLOSE_TAG = b"<!--EndFragment--></body></html>"


def _make_cf_html(fragment: str) -> bytes:
    """Wrap an HTML fragment in a properly-headered CF_HTML clipboard blob."""
    # Compute header length with zeroed offsets (all offsets are 9 digits = same byte length)
    dummy_header = _CF_HTML_HEADER_TEMPLATE.format(sh=0, eh=0, sf=0, ef=0)
    header_len = len(dummy_header.encode("utf-8"))

    frag_bytes = fragment.encode("utf-8")

    sh = header_len
    sf = sh + len(_OPEN_TAG)
    ef = sf + len(frag_bytes)
    eh = ef + len(_CLOSE_TAG)

    header = _CF_HTML_HEADER_TEMPLATE.format(sh=sh, eh=eh, sf=sf, ef=ef)
    return header.encode("utf-8") + _OPEN_TAG + frag_bytes + _CLOSE_TAG


# ── Public API ────────────────────────────────────────────────────────────────

def convert_to_clipboard(text: str, fmt: str) -> dict:
    """Convert *text* from *fmt* and write the result to the Windows clipboard.

    Parameters
    ----------
    text:
        Source text in Markdown or LaTeX.
    fmt:
        ``"markdown"`` or ``"latex"``.

    Returns
    -------
    dict
        ``{"formats_written": [...], "warnings": [...]}``

    Raises
    ------
    ValueError
        For an unknown *fmt*.
    RuntimeError
        If conversion fails (e.g. Pandoc not installed).
    """
    if fmt not in _PANDOC_INPUT:
        raise ValueError(f"Unknown format {fmt!r}. Expected 'markdown' or 'latex'.")

    pandoc_in = _PANDOC_INPUT[fmt]
    warnings: list[str] = []

    # ── Pre-process math spacing ──────────────────────────────────────────────
    text = _preprocess_math_spacing(text, fmt)

    # ── Convert to HTML with MathML ───────────────────────────────────────────
    # We do NOT generate CF_RTF. Pandoc's RTF/OMML writer drops all LaTeX
    # math-spacing commands (\ , \, , \quad …) with no workaround.
    # Pandoc's MathML writer handles them correctly via <mspace>, and
    # Word 2016+ pastes MathML from CF_HTML natively.
    html_fragment: str | None = None
    try:
        html_fragment = _pandoc(text, pandoc_in, "html", ["--mathml"])
    except FileNotFoundError:
        raise RuntimeError(
            "Pandoc is not installed or not on PATH. "
            "Install it from https://pandoc.org/installing.html"
        )
    except Exception as exc:
        raise RuntimeError(f"Conversion failed: {exc}")

    # ── Write CF_HTML to clipboard ────────────────────────────────────────────
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(CF_HTML_FORMAT, _make_cf_html(html_fragment))
    finally:
        win32clipboard.CloseClipboard()

    return {"formats_written": ["HTML"], "warnings": warnings}
