# Changelog

## 2026-06-10

### Feat: Quiz Markdown → Word (clipboard + DOCX)

**Files:** `backend/quiz_to_word.py` (new), `backend/main.py`, `frontend/src/api.ts`,
`frontend/src/components/QuizPanel.tsx`

New reverse direction: astro-dev-id quiz markdown pasted into Word with correct
named paragraph styles (`P - Problem`, `P - Sub-problem`, `Solution - Title`,
`Solution`).  Two output paths:

- **Copy to Clipboard** — builds CF_HTML with `mso-style-name` mappings and
  MathML (via Pandoc `--mathml`) so Word applies existing named styles on paste.
- **Download DOCX** — converts to Pandoc custom-style fenced-div markdown and
  calls Pandoc `-t docx`.  Math converts to OMML.  Pass a `reference_doc` that
  defines the named styles to get proper paragraph formatting.

---

### Fix: Word-origin meta tags required for `mso-style-name` mapping

**File:** `backend/quiz_to_word.py` — `_HTML_HEAD`

Word only looks up `mso-style-name` mappings when the pasted HTML carries
`<meta name="ProgId" content="Word.Document">` and
`<meta name="Generator" content="Microsoft Word 15">`, plus
`xmlns:o` / `xmlns:w` on the `<html>` tag.  Without these, Word ignores the
class names and applies "Normal" to everything.

**Fix:** Added the required meta tags and XML namespace attributes to
`_HTML_HEAD`.

---

### Fix: `mso-style-name` values must include spaces around hyphens

**File:** `backend/quiz_to_word.py` — `_QUIZ_MSO_STYLES`

The CSS `mso-style-name` values must exactly match the internal Word style
names.  The actual names are `"P - Problem"`, `"P - Sub-problem"`,
`"Solution - Title"` (spaces around hyphens), not the CSS-safe hyphenated
forms.

**Fix:** Updated all four `mso-style-name` declarations to use the correct
names with spaces.

---

### Fix: Space after inline math lost on paste

**File:** `backend/quiz_to_word.py` — `_fix_math_spacing`

Word's MathML→OMML conversion during paste strips bare whitespace (spaces,
newlines) immediately following a `</math>` closing tag.  Text that came
after an equation was concatenated with the equation number (e.g., "3,44dan"
instead of "3,44 dan").

**Fix:** Replace every whitespace run after `</math>` with `&#160;`
(HTML non-breaking space entity, U+00A0).  Being an explicit entity — not bare
whitespace — Word preserves it through the OMML conversion.  Pattern:
`_MATH_CLOSE_RE = re.compile(r"(</math>)\s+", re.IGNORECASE)`.

---

### Fix: "Jawaban" line not bold on paste

**File:** `backend/quiz_to_word.py` — `questions_to_word_html`, `_QUIZ_MSO_STYLES`

The `Solution - Title` paragraph style has `font-weight:bold` defined at the
style level in the Word document, not as a character override.  Our previous
`<b style="font-weight:bold">` added a character-level run that Word discarded
or overrode during style application.

**Fix:** Removed the `<b>` wrapper.  Added
`font-weight:bold;mso-bidi-font-weight:normal;` directly to the CSS rule for
`.Solution-Title` in `_QUIZ_MSO_STYLES`.  Bold now comes from the paragraph
style (or the CSS fallback if the style doesn't exist in the target document).

---

### Fix: DOCX custom-style names didn't match Word style names

**File:** `backend/quiz_to_word.py` — `_to_pandoc_custom_style_md`

Pandoc's fenced-div `custom-style` attribute must exactly match the named
paragraph style in the reference `.docx` template for the style to be applied.
The function was using CSS-safe names (`"P-Problem"`, `"Solution-Title"`) which
Pandoc treated as new unknown styles, creating unstyled paragraphs.

**Fix:** Changed all four custom-style names to the exact Word style names:
`"P - Problem"`, `"P - Sub-problem"`, `"Solution - Title"`, `"Solution"`.

---

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
