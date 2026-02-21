"""Windows clipboard reading via pywin32."""

from __future__ import annotations

import time

import win32clipboard


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

        return {
            "formats": formats,
            "has_html": has_html,
            "raw_html": raw_html[:50000],  # cap at 50KB for display
            "plain_text": plain_text[:30000],  # cap at 30K chars for display
        }
    except Exception as e:
        return {
            "formats": [],
            "has_html": False,
            "raw_html": "",
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
        # CF_HTML has a header like "Version:0.9\nStartHTML:..."
        # The actual HTML starts after "StartHTML:<offset>"
        idx = text.find("<html") if "<html" in text.lower() else text.find("<HTML")
        if idx == -1:
            # fallback: look for StartHTML offset
            for line in text.splitlines():
                if line.startswith("StartHTML:"):
                    idx = int(line.split(":")[1])
                    break
        return text[idx:] if idx >= 0 else text
    except Exception:
        return None
    finally:
        win32clipboard.CloseClipboard()
