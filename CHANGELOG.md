# Changelog

## 2026-03-15

### Fix: `[?]` glyphs in `.docx` export — encoding

**File:** `backend/main.py` — `/api/export/docx` handler

**Problem:** Curly apostrophes and smart quotes (U+2018, U+2019, U+201C, U+201D) rendered
as `[?]` in the exported `.docx` file.

**Root cause:** `subprocess.run(..., text=True)` uses the OS default encoding on
Windows (cp1252). Characters outside cp1252 (curly quotes, non-ASCII math text, etc.)
were silently corrupted before reaching Pandoc.

**Fix:** Pass the input as UTF-8 bytes (`input=text.encode("utf-8")`) instead of using
`text=True`, consistent with the approach already used in `to_clipboard.py`.

---

### Fix: Code blocks not monospaced when using "Copy to Word"

**File:** `backend/to_clipboard.py`

**Problem:** Fenced code blocks pasted from the clipboard into Word appeared in a
proportional font (no monospace), indistinguishable from regular paragraph text.

**Root cause:** Pandoc's HTML output without `--standalone` contains no CSS. Word
receives `<pre><code>` elements with no style attribute and falls back to its default
body font.

**Fix:** Added `_apply_word_html_styles()` post-processor that injects inline
`style="font-family: Consolas, 'Courier New', monospace; ..."` directly onto every
`<pre>` and `<code>` element in the HTML fragment before it is written to the clipboard.

---

### Fix: LaTeX and HTML preview renderers non-functional

**Files:** `frontend/src/components/Preview.tsx`, `frontend/src/App.css`

**Problem:** The LaTeX preview showed raw LaTeX source instead of formatted output.
The HTML preview lost all browser-default styling (lists, headings, code blocks) due to
`all: initial` in the CSS.

**Fix (LaTeX):** Rewrote `renderLatex` with a `latexToHtml()` converter that handles
sections, text formatting, list environments, verbatim blocks, special characters,
and paragraph splitting, while extracting all math spans and rendering them with KaTeX.

**Fix (HTML):** Removed `all: initial` from `.preview-html` and added explicit child-element
styles (headings, lists, code, blockquote, table, etc.) scoped under `.preview-html`.
Also added matching element styles under `.preview-latex` so the generated HTML renders
with proper typography.
