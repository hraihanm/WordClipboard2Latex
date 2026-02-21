"""Convert Markdown / LaTeX text to Word-compatible clipboard content.

Strategy
--------
1. Run Pandoc twice:
   - ``→ rtf  --standalone``      : full RTF document, Word reads natively
   - ``→ html  --mathml``         : HTML fragment with MathML; Word 2013+ renders it
2. Both formats are written to the Windows clipboard so Word can pick the
   richest format it understands.

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

CF_RTF = win32clipboard.RegisterClipboardFormat("Rich Text Format")
CF_HTML_FORMAT = win32clipboard.RegisterClipboardFormat("HTML Format")

# Pandoc input format strings for each supported source format.
_PANDOC_INPUT: dict[str, str] = {
    "markdown": "markdown+tex_math_dollars+tex_math_single_backslash",
    "latex": "latex",
}


# ── Math spacing pre-processor ────────────────────────────────────────────────

def _preprocess_math_spacing(text: str, fmt: str) -> str:
    r"""Replace LaTeX spacing commands that Pandoc drops in RTF/OMML output.

    When Pandoc converts math to RTF (via OMML), it silently discards ``\ ``
    (backslash-space, the LaTeX thick space) because OMML has no direct
    equivalent spacing primitive for it.

    Replacing ``\ `` with ``\text{ }`` works around this: Pandoc converts
    ``\text{ }`` to an OMML text run containing a literal space character,
    which Word then renders as a visible gap — e.g. ``1\,\text{AU}`` displays
    as "1 AU" instead of "1AU".

    For Markdown input only the content inside ``$...$`` and ``$$...$$`` math
    delimiters is touched; prose text is left alone.
    """
    def _fix(math: str) -> str:
        # \  (backslash-space) → \text{ }
        return re.sub(r'\\ ', r'\\text{ }', math)

    if fmt == 'latex':
        # The whole document is LaTeX — apply globally.
        return _fix(text)

    # Markdown: only replace inside math delimiters.
    # Handle $$...$$ (display) before $...$ (inline) to avoid mis-matching.
    def fix_display(m: re.Match) -> str:
        return '$$' + _fix(m.group(1)) + '$$'

    def fix_inline(m: re.Match) -> str:
        return '$' + _fix(m.group(1)) + '$'

    text = re.sub(r'\$\$([\s\S]*?)\$\$', fix_display, text)
    text = re.sub(r'\$([^$\n]+?)\$', fix_inline, text)
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
        If all conversions fail (e.g. Pandoc not installed).
    """
    if fmt not in _PANDOC_INPUT:
        raise ValueError(f"Unknown format {fmt!r}. Expected 'markdown' or 'latex'.")

    # Fix spacing commands that Pandoc drops in RTF/OMML output (e.g. `\ `)
    text = _preprocess_math_spacing(text, fmt)

    pandoc_in = _PANDOC_INPUT[fmt]
    warnings: list[str] = []
    rtf: str | None = None
    html_fragment: str | None = None

    # ── RTF conversion ────────────────────────────────────────────────────────
    try:
        rtf = _pandoc(text, pandoc_in, "rtf", ["--standalone"])
    except FileNotFoundError:
        warnings.append("Pandoc not found — RTF output skipped.")
    except Exception as exc:
        warnings.append(f"RTF conversion failed: {exc}")

    # ── HTML conversion (fragment, MathML for equations) ─────────────────────
    try:
        html_fragment = _pandoc(text, pandoc_in, "html", ["--mathml"])
    except FileNotFoundError:
        warnings.append("Pandoc not found — HTML output skipped.")
    except Exception as exc:
        warnings.append(f"HTML conversion failed: {exc}")

    if not rtf and not html_fragment:
        raise RuntimeError(
            "All conversions failed. Is Pandoc installed?\n" + "\n".join(warnings)
        )

    # ── Write to clipboard ────────────────────────────────────────────────────
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        if rtf:
            # RTF is traditionally ASCII/latin-1; encode as cp1252 for safety.
            # Pandoc marks the codepage in the RTF header so this is correct.
            win32clipboard.SetClipboardData(CF_RTF, rtf.encode("cp1252", errors="replace"))
        if html_fragment:
            win32clipboard.SetClipboardData(CF_HTML_FORMAT, _make_cf_html(html_fragment))
    finally:
        win32clipboard.CloseClipboard()

    formats_written = []
    if rtf:
        formats_written.append("RTF")
    if html_fragment:
        formats_written.append("HTML")

    return {"formats_written": formats_written, "warnings": warnings}
