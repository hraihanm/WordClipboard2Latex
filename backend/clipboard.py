"""Windows clipboard reading via pywin32."""

from __future__ import annotations

import time

import win32clipboard
from bs4 import BeautifulSoup


CF_HTML = win32clipboard.RegisterClipboardFormat("HTML Format")

# Well-known clipboard format names for display
_KNOWN_FORMATS: dict[int, str] = {
    1: "CF_TEXT",
    2: "CF_BITMAP",
    7: "CF_OEMTEXT",
    13: "CF_UNICODETEXT",
    16: "CF_LOCALE",
    CF_HTML: "HTML Format",
}


def _strip_cf_html_prefix(text: str) -> str:
    """Strip CF_HTML metadata so the string starts at the HTML document."""
    if not text:
        return text
    lower = text.lower()
    idx = lower.find("<html")
    if idx == -1:
        for line in text.splitlines():
            if line.startswith("StartHTML:"):
                try:
                    idx = int(line.split(":", 1)[1].strip())
                except ValueError:
                    idx = -1
                break
    return text[idx:] if idx >= 0 else text


def _extract_html_body_inner(html_doc: str) -> str:
    """Inner HTML of <body>, or document contents if no body tag."""
    soup = BeautifulSoup(html_doc, "lxml")
    body = soup.body
    if body:
        return body.decode_contents()
    return soup.decode_contents()


def _open_clipboard(retries: int = 5, delay: float = 0.05) -> None:
    """Open the clipboard with retries to handle transient lock contention."""
    for i in range(retries):
        try:
            win32clipboard.OpenClipboard()
            return
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(delay)


def read_clipboard_debug() -> dict:
    """Return debug info about clipboard contents: available formats and raw HTML."""
    _open_clipboard()
    try:
        formats: list[dict] = []
        fmt = 0
        while True:
            fmt = win32clipboard.EnumClipboardFormats(fmt)
            if fmt == 0:
                break
            name = _KNOWN_FORMATS.get(fmt)
            if name is None:
                try:
                    name = win32clipboard.GetClipboardFormatName(fmt)
                except Exception:
                    name = f"Format#{fmt}"
            formats.append({"id": fmt, "name": name})

        # Get raw HTML if available
        raw_html = ""
        if win32clipboard.IsClipboardFormatAvailable(CF_HTML):
            try:
                raw: bytes = win32clipboard.GetClipboardData(CF_HTML)
                raw_html = raw.decode("utf-8", errors="replace")
            except Exception:
                raw_html = "(failed to read)"

        # Get plain text for comparison
        plain_text = ""
        if win32clipboard.IsClipboardFormatAvailable(13):  # CF_UNICODETEXT
            try:
                plain_text = win32clipboard.GetClipboardData(13)
            except Exception:
                plain_text = "(failed to read)"

        has_html = any(f["name"] == "HTML Format" for f in formats)

        raw_html_body = ""
        if raw_html and raw_html != "(failed to read)":
            doc = _strip_cf_html_prefix(raw_html)
            if doc.strip():
                try:
                    raw_html_body = _extract_html_body_inner(doc)
                except Exception:
                    raw_html_body = "(failed to parse body)"

        return {
            "formats": formats,
            "has_html": has_html,
            "raw_html": raw_html,
            "raw_html_body": raw_html_body,
            "plain_text": plain_text,
        }
    except Exception as e:
        return {
            "formats": [],
            "has_html": False,
            "raw_html": "",
            "raw_html_body": "",
            "plain_text": "",
            "error": str(e),
        }
    finally:
        win32clipboard.CloseClipboard()


def read_clipboard_html() -> str | None:
    """Read CF_HTML from the Windows clipboard.

    Returns the HTML string (after stripping the CF_HTML header) or None
    if the clipboard does not contain HTML data.
    """
    _open_clipboard()
    try:
        if not win32clipboard.IsClipboardFormatAvailable(CF_HTML):
            return None
        raw: bytes = win32clipboard.GetClipboardData(CF_HTML)
        text = raw.decode("utf-8", errors="replace")
        return _strip_cf_html_prefix(text)
    except Exception:
        return None
    finally:
        win32clipboard.CloseClipboard()
