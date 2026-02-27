# WordClipboard2LaTeX

A local web application that bridges Microsoft Word and LaTeX/Markdown. Copy an equation or formatted text from Word, click a button, and get clean LaTeX, Markdown, and HTML — or go the other way and paste LaTeX/Markdown directly back into Word as a native rendered equation.

---

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [Usage](#usage)
  - [Word → LaTeX / Markdown / HTML](#word--latex--markdown--html)
  - [LaTeX / Markdown → Word](#latex--markdown--word)
  - [Keyboard Shortcuts](#keyboard-shortcuts)
- [Architecture](#architecture)
  - [Data Flow: Word → Text](#data-flow-word--text)
  - [Data Flow: Text → Word](#data-flow-text--word)
- [Backend Reference](#backend-reference)
  - [API Endpoints](#api-endpoints)
  - [Module Reference](#module-reference)
- [Frontend Reference](#frontend-reference)
  - [Component Tree](#component-tree)
  - [API Client](#api-client)
- [Technical Deep Dives](#technical-deep-dives)
  - [OMML Preservation via Placeholder Extraction](#omml-preservation-via-placeholder-extraction)
  - [Math Spacing in Word → LaTeX](#math-spacing-in-word--latex)
  - [Math Spacing in LaTeX → Word](#math-spacing-in-latex--word)
  - [Why CF_HTML and not CF_RTF](#why-cf_html-and-not-cf_rtf)
  - [LaTeX Post-Processing Pipeline](#latex-post-processing-pipeline)
- [Project Structure](#project-structure)

---

## Features

| Direction | Capability |
|---|---|
| Word → LaTeX | Equations (OMML), bold, italic, headings, lists, tables |
| Word → Markdown | All the above in Markdown syntax |
| Word → HTML | Clean semantic HTML, stripped of Word-specific cruft |
| LaTeX → Word | Renders equations natively in Word 2016+ via MathML |
| Markdown → Word | Full Markdown with inline and display math |
| Live Preview | Side-by-side code and rendered preview with KaTeX |
| Dark / Light Mode | System-preference aware, toggle in header |
| Debug View | Clipboard format inspector and raw HTML dump |

---

## Requirements

- **Windows 10 / 11** (clipboard access via `pywin32` is Windows-only)
- **Python 3.10+**
- **Node.js 18+**
- **[Pandoc](https://pandoc.org/installing.html)** — `start.bat` adds `C:\Program Files\Pandoc` to PATH automatically; edit `PANDOC_PATH` in `start.bat` if installed elsewhere
- **Microsoft Word** — source or destination of clipboard content

---

## Quick Start

### Windows

```bat
start.bat
```

`start.bat` creates a Python venv in `backend/venv`, installs dependencies, adds Pandoc to PATH, and starts both servers. For OCR (image → LaTeX), copy `backend/.env.example` to `backend/.env` and add your `GEMINI_API_KEY`.

### Linux / macOS (dev / WSL)

```bash
chmod +x start.sh
./start.sh
```

Both scripts install dependencies, start the backend on **port 8741** and the frontend dev server on **port 5173**, then open the app.

Open **http://localhost:5173** in your browser.

### Manual start

**Backend**

```bash
cd backend
python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
uvicorn main:app --reload --port 8741
```

**Frontend** (separate terminal)

```bash
cd frontend
npm install
npm run dev
```

### Production build

```bash
cd frontend
npm run build          # outputs to frontend/dist/
```

The backend automatically serves `frontend/dist/` as static files when the directory exists, so the entire app runs on **http://localhost:8741** with no separate dev server needed.

---

## Usage

### Word → LaTeX / Markdown / HTML

1. In Microsoft Word, select the text or equations you want to convert.
2. Copy it (`Ctrl+C`).
3. Switch to the browser tab running WordClipboard2LaTeX.
4. Click **Convert from Clipboard** (or press `Ctrl+Shift+V`).
5. The result appears in the **Code** panel (raw source) and **Preview** panel (rendered).
6. Use the **Markdown / LaTeX / HTML** tabs to switch between output formats.
7. Click the copy icon in the Code panel to copy the raw source to your clipboard.

### LaTeX / Markdown → Word

1. Scroll down to the **Text → Word Clipboard** section.
2. Select the input format tab (**Markdown** or **LaTeX**).
3. Paste or type your source text in the textarea.
4. Click **Copy to Word** (or press `Ctrl+Enter` inside the textarea).
5. Switch to Word and paste (`Ctrl+V`). Equations render natively.

### Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Shift+V` | Convert clipboard (Word → Text) |
| `Ctrl+Enter` | Copy to Word (in the LaTeX/Markdown textarea) |

---

## Architecture

```
┌─────────────────────────────────────────────┐
│                  Browser                    │
│  ┌──────────────────────────────────────┐  │
│  │        React Frontend (Vite)         │  │
│  │  App.tsx · Preview · ToWordPanel … │  │
│  └──────────────┬───────────────────────┘  │
│                 │ fetch /api/*              │
└─────────────────┼───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│           FastAPI Backend (Python)          │
│                                             │
│  main.py                                   │
│    ├── GET  /api/convert                   │
│    │     clipboard.py → parser.py          │
│    │     → omml_to_latex.py               │
│    │     → html_to_latex/markdown/html.py │
│    │     → postprocess.py                 │
│    │     → converter.py (orchestrator)    │
│    │                                      │
│    └── POST /api/to-clipboard             │
│          to_clipboard.py                  │
│            → _preprocess_math_spacing()  │
│            → pandoc --mathml             │
│            → win32clipboard              │
└─────────────────────────────────────────────┘
                  │
         Windows Clipboard (pywin32)
                  │
         Microsoft Word
```

### Data Flow: Word → Text

```
Word  ──Ctrl+C──▶  Windows Clipboard (CF_HTML + OMML math blocks)
                        │
                   clipboard.py
                   read_clipboard_html()
                        │
                   parser.py
                   ┌────────────────────────────────────────────┐
                   │ 1. Extract OMML blocks → store as placeholders │
                   │ 2. BeautifulSoup parses the cleaned HTML   │
                   │ 3. Walk DOM → build DocNode tree           │
                   │    (HEADING, PARAGRAPH, LIST, TABLE,       │
                   │     INLINE_MATH, DISPLAY_MATH)             │
                   └────────────────────────────────────────────┘
                        │  DocNode list
                   converter.py
                   ┌────────────────────────────────────────────┐
                   │ For each DocNode:                          │
                   │  MATH → omml_to_latex.py                  │
                   │          wrap in .docx → pandoc → LaTeX   │
                   │          postprocess.py                   │
                   │  TEXT/HEADING/LIST/TABLE →                │
                   │          html_to_latex.py   (LaTeX)       │
                   │          html_to_markdown.py (Markdown)   │
                   │          html_to_html.py     (HTML)       │
                   └────────────────────────────────────────────┘
                        │  {latex, markdown, html, warnings}
                   Frontend renders in Code + Preview panels
```

### Data Flow: Text → Word

```
User types LaTeX/Markdown in ToWordPanel
        │
   POST /api/to-clipboard  {text, format}
        │
   to_clipboard.py
   ┌──────────────────────────────────────────────┐
   │ 1. _preprocess_math_spacing()               │
   │    Replace spacing cmds before \text{} with │
   │    ~ (non-breaking space inside \text{})    │
   │                                              │
   │ 2. pandoc -f markdown/latex -t html --mathml│
   │    Converts to HTML with MathML equations   │
   │                                              │
   │ 3. _make_cf_html()                          │
   │    Wrap in CF_HTML header with byte offsets │
   │                                              │
   │ 4. win32clipboard.SetClipboardData()        │
   └──────────────────────────────────────────────┘
        │
Word ──Ctrl+V──▶ Renders HTML + MathML natively (Word 2016+)
```

---

## Backend Reference

### API Endpoints

#### `GET /api/health`

Returns backend and Pandoc status.

```json
{
  "status": "ok",
  "pandoc_installed": true,
  "pandoc_version": "pandoc 3.6.1"
}
```

#### `GET /api/clipboard-info`

Debug endpoint. Returns all clipboard formats currently available plus the raw HTML and plain text content.

```json
{
  "formats": [
    {"id": 13, "name": "CF_UNICODETEXT"},
    {"id": 49381, "name": "HTML Format"}
  ],
  "has_html": true,
  "raw_html": "...",
  "plain_text": "..."
}
```

#### `GET /api/convert`

Reads the Windows clipboard and converts to LaTeX, Markdown, and HTML.

```json
{
  "latex": "\\[E = mc^2\\]",
  "markdown": "$$E = mc^2$$",
  "html": "<p><span class=\"math display\">E = mc^2</span></p>",
  "warnings": []
}
```

#### `POST /api/to-clipboard`

Converts source text to Word-compatible clipboard content.

**Request body**

```json
{
  "text": "$E = mc^2$",
  "format": "markdown"
}
```

`format` is `"markdown"` or `"latex"`.

**Response**

```json
{
  "formats_written": ["HTML"],
  "warnings": []
}
```

#### `POST /api/convert/text`

Converts a raw HTML+OMML string (useful for testing without a live clipboard).

**Request body**

```json
{"html": "<p>...</p><m:oMath>...</m:oMath>"}
```

**Response**: same shape as `GET /api/convert`.

---

### Module Reference

#### `clipboard.py`

Low-level Windows clipboard I/O via `pywin32`.

| Function | Description |
|---|---|
| `read_clipboard_html()` | Returns the CF_HTML content as a string, strips the CF_HTML header |
| `read_clipboard_debug()` | Returns all available formats, raw HTML (≤ 50 KB), plain text (≤ 30 K chars) |

Clipboard locking is handled with exponential backoff — Word holds the lock briefly after a copy, so the code retries up to 5 times before failing.

---

#### `parser.py`

Converts raw clipboard HTML into a typed `DocNode` list.

```python
@dataclass
class DocNode:
    type: NodeType         # HEADING | PARAGRAPH | LIST | TABLE | INLINE_MATH | DISPLAY_MATH | TEXT
    content: str           # HTML-formatted inline content or LaTeX math string
    level: int             # Heading level (1–6) or list depth
    items: list            # List items or table rows
    math_env: str | None   # "aligned", "multiline", "pmatrix", etc.
```

**Key design: OMML placeholder extraction**

Before passing HTML to BeautifulSoup, the parser extracts every `<m:oMath>` block, stores it in a dict, and replaces it with `<omml-display data-id="N">` or `<omml-inline data-id="N">`. After parsing, the placeholders are resolved back to the original OMML. This prevents BeautifulSoup from lowercasing OMML tag names (which would break Pandoc's XML parser).

---

#### `omml_to_latex.py`

Converts a single OMML XML fragment to a LaTeX math string.

**Process**

1. Strip HTML formatting tags (`<font>`, `<span>`, `<i>`, `<br>`, …) that Word inserts into clipboard OMML.
2. Wrap bare text in `<m:r>` with `<m:t xml:space="preserve">` (Pandoc requires `<m:t>` to extract text; `xml:space="preserve"` preserves spacing inside math runs).
3. Restore proper casing of OMML tag names after any lowercasing by BeautifulSoup.
4. Pack into a minimal in-memory `.docx` zip.
5. Write to a temp file and call `pandoc input.docx -f docx -t latex --wrap=none`.
6. Strip Pandoc's math delimiters (`\[...\]` or `$...$`) to return bare LaTeX.
7. Pass through `postprocess_latex()`.

If Pandoc times out or fails, falls back to stripping all XML tags and returning plain text.

---

#### `postprocess.py`

Cleans up Pandoc's raw LaTeX output. Applied after every OMML conversion.

| Pass | Function | What it fixes |
|---|---|---|
| 1 | `_unwrap_multiline_groups` | Converts `{line1}{line2}…` to `line1 \\ line2 …` |
| 2 | `_unwrap_array_in_aligned` | Removes `\begin{array}{r}…\end{array}` wrappers inside aligned |
| 3 | `_collapse_nested_aligned` | Collapses double `\begin{aligned}…\begin{aligned}` |
| 4 | `_add_alignment_markers` | Inserts `&` before the first relation operator on each line |
| 5 | `_fix_bold_math_vars` | Strips `\mathbf{x}` → `x` for single-character variables |
| 6 | `_fix_log_subscript` | Fixes `\log\ _{10}` → `\log_{10}` |
| 7 | `_fix_whitespace` | Normalizes spaces and line endings |
| 8 | `_fix_common_pandoc_quirks` | Removes `\text{ }`, empty `{}`, fixes `\left`/`\right` spacing |
| 9 | `_fix_number_unit_spacing` | Inserts `\,` between a digit and `\text{unit}` (ISO 80000 style) |

**Relation operators** recognised for alignment: `=`, `<`, `>`, `\approx`, `\simeq`, `\cong`, `\equiv`, `\sim`, `\propto`, `\leq`, `\geq`, `\ll`, `\gg`, `\neq`, `\to`, `\rightarrow`, `\leftarrow`, `\Rightarrow`, `\Leftarrow`, `\Leftrightarrow`, `\iff`.

---

#### `converter.py`

Orchestrates the full conversion for a list of `DocNode`s, returning `{latex, markdown, html, warnings}`.

- Math nodes are sent to `omml_to_latex()`.
- Text/heading/list/paragraph nodes go to each of the three HTML→format converters simultaneously.
- Tables are rendered to `\begin{tabular}` (LaTeX), pipe-table (Markdown), and `<table>` (HTML). Math cells are forced to inline (`$...$`) to avoid line-wrapping issues.

---

#### `html_to_latex.py` / `html_to_markdown.py` / `html_to_html.py`

Three parallel converters that turn formatted HTML (bold, italic, headings, lists) into their respective output formats.

**Formatting mapping**

| HTML | LaTeX | Markdown |
|---|---|---|
| `<b>` / `<strong>` | `\textbf{…}` | `**…**` |
| `<i>` / `<em>` | `\textit{…}` | `*…*` |
| `<u>` | `\underline{…}` | `<u>…</u>` |
| `<sup>` | `\textsuperscript{…}` | `<sup>…</sup>` |
| `<sub>` | `\textsubscript{…}` | `<sub>…</sub>` |
| `<h1>` | `\section{…}` | `# …` |
| `<h2>` | `\subsection{…}` | `## …` |
| `<h3>` | `\subsubsection{…}` | `### …` |
| `<ul>` | `\begin{itemize}…` | `- …` |
| `<ol>` | `\begin{enumerate}…` | `1. …` |

`html_to_html.py` strips Word-specific attributes (`style`, `class="Mso*"`, `data-*`, `xml:lang`) and returns clean semantic HTML.

---

#### `to_clipboard.py`

Converts Markdown or LaTeX source text to a Word-compatible clipboard payload.

| Function | Description |
|---|---|
| `convert_to_clipboard(text, fmt)` | Main entry point. Pre-processes, converts with Pandoc, writes to clipboard |
| `_preprocess_math_spacing(text, fmt)` | Applies spacing fix to all math spans |
| `_fix_math_spacing(math)` | Core regex transform (see [Technical Deep Dives](#math-spacing-in-latex--word)) |
| `_pandoc(text, from_fmt, to_fmt, extra_args)` | Thin subprocess wrapper for Pandoc |
| `_make_cf_html(fragment)` | Builds CF_HTML byte blob with correct offset header |

---

## Frontend Reference

### Component Tree

```
App
├── Header
│   ├── Title
│   └── ThemeToggle / PandocWarning
├── ConvertSection
│   ├── ConvertButton       — triggers GET /api/convert
│   └── ShortcutHint
├── ErrorBox (conditional)
├── OutputGrid (shown after first conversion)
│   ├── Code Panel
│   │   ├── OutputTabs      — Markdown | LaTeX | HTML
│   │   ├── CopyButton
│   │   └── CodeOutput      — <pre><code> display
│   └── Preview Panel
│       ├── OutputTabs      — independent tab state
│       └── Preview         — KaTeX + Marked rendering
├── ToWordPanel             — POST /api/to-clipboard
│   ├── FormatTabs          — Markdown | LaTeX
│   ├── Textarea
│   ├── CopyToWordButton
│   └── StatusFooter
└── DebugSection (collapsible)
    ├── ClipboardFormatsTable
    ├── RawHTMLPre
    └── PlainTextPre
```

### API Client

`frontend/src/api.ts` exports typed async functions:

```ts
convertClipboard(): Promise<ConvertResult>
convertText(html: string): Promise<ConvertResult>
healthCheck(): Promise<HealthResult>
clipboardInfo(): Promise<ClipboardInfo>
toClipboard(text: string, format: 'markdown' | 'latex'): Promise<ToClipboardResult>
```

The Vite dev server proxies all `/api/*` requests to `http://localhost:8741` so the browser never needs to deal with CORS in development.

### Preview Component

`Preview.tsx` renders three modes:

**Markdown mode** — math-aware Markdown rendering:
1. Extract all `$$...$$` (display) and `$...$` (inline) spans, store with IDs.
2. Replace with `<span data-math-id="N">` placeholders.
3. Pass the cleaned string to [Marked](https://marked.js.org/) for HTML conversion.
4. Re-inject KaTeX-rendered math into the resulting HTML.

This two-pass approach prevents Marked from mis-interpreting LaTeX syntax as Markdown elements.

**LaTeX mode** — splits on `\[...\]` and `$...$` delimiters, renders each math block with KaTeX, interleaves with plain text.

**HTML mode** — direct `innerHTML` assignment.

---

## Technical Deep Dives

### OMML Preservation via Placeholder Extraction

Word's clipboard HTML embeds OMML equations like this:

```html
<!--[if gte msEquation 12]>
<m:oMath>
  <m:r><m:t>E</m:t></m:r>
  <m:r><m:t>=</m:t></m:r>
  <m:r><m:t>mc</m:t></m:r>
  <m:sSup><m:e><m:r><m:t>2</m:t></m:r></m:e></m:sSup>
</m:oMath>
<![endif]-->
```

**The problem**: BeautifulSoup (lxml parser) lowercases all tag names, turning `m:oMath` → `m:omath`, `m:sSup` → `m:ssup`, etc. Pandoc's XML parser is case-sensitive and rejects lowercase OMML tags.

**The solution** (`parser.py`):
1. Before calling BeautifulSoup, scan the raw HTML with a regex and extract every `<m:oMath>…</m:oMath>` block.
2. Store each block in a dict with an integer ID.
3. Replace each block with a harmless placeholder: `<omml-display data-id="0"></omml-display>`.
4. Parse the simplified HTML with BeautifulSoup normally.
5. During the DOM walk, when a placeholder is encountered, retrieve the original OMML from the dict.
6. Pass the pristine OMML to `omml_to_latex.py`.

`omml_to_latex.py` adds a second safety layer: `_restore_omml_case()` maps any remaining lowercase OMML tag names back to their proper case using a 50-entry lookup table.

---

### Math Spacing in Word → LaTeX

**Problem**: When Word stores a number followed by a unit (e.g. `5407 Å`) in an equation, the space lives in a separate `<m:r>` (math run) element. The `_wrap_bare_text_in_mt` function previously called `.strip()` on bare text inside `<m:r>`, silently dropping the space. Even if the space survived, plain spaces in LaTeX math mode are invisible — the standard typographic convention (ISO 80000) calls for a thin space `\,`.

**Fix** (in `omml_to_latex.py` and `postprocess.py`):

1. `_wrap_bare_text_in_mt` now uses `xml:space="preserve"` on `<m:t>` elements whose content contains whitespace, preventing XML parsers from stripping it.
2. `_fix_number_unit_spacing` (in `postprocess.py`) applies after Pandoc:
   ```
   (\d)\s*(\\text{)  →  \1\,\2
   ```
   This inserts `\,` (thin space) between any digit and the following `\text{…}` unit label, regardless of whether a space survived the OMML extraction.

Result: `5407\text{Å}` → `5407\,\text{Å}`.

---

### Math Spacing in LaTeX → Word

**Problem**: When users write `$1\ \text{AU}$` (backslash-space before a unit), Word displays "1AU" with no gap. Three root causes:

1. Pandoc's MathML writer drops `\ `, `\,`, `\quad` and other explicit spacing commands when they appear immediately before `\text{}`.
2. Pandoc also strips leading spaces inside `\text{ content}`.
3. XML whitespace is not preserved by Word's clipboard parser.

**Solution** — preprocessing in `to_clipboard.py`:

The key insight is that `~` in LaTeX text mode is a non-breaking space (U+00A0). When Pandoc converts `\text{~AU}` to MathML it emits `&#160;` — a character entity, not XML whitespace — which neither Pandoc nor Word can strip.

The preprocessing (`_preprocess_math_spacing`) applies two regex transforms to every math span before calling Pandoc:

| Input | Output | Description |
|---|---|---|
| `1\ \text{AU}` | `1\text{~AU}` | `\ ` before `\text{}` → `~` inside |
| `1\quad\text{m}` | `1\text{~m}` | `\quad` before `\text{}` → `~` inside |
| `5407\,\text{Å}` | `5407\text{~Å}` | `\,` before `\text{}` → `~` inside |
| `\text{ AU}` | `\text{~AU}` | leading space inside `\text{}` → `~` |
| `x\text{th}` | `x\text{th}` | ordinal suffix — unchanged |

Spacing commands handled: `\ `, `\,`, `\;`, `\:`, `\>`, `\quad`, `\qquad`, `\enspace`, `\thinspace`, `\medspace`, `\thickspace`.

For Markdown input the transform is applied only inside `$…$` and `$$…$$` spans; for LaTeX input it is applied to the entire document.

---

### Why CF_HTML and not CF_RTF

Word accepts several clipboard formats and prefers CF_RTF (Rich Text Format) over CF_HTML when both are present. RTF would seem like the natural choice since Word uses OMML internally, and Pandoc can output RTF. However:

- **Pandoc's RTF writer uses OMML** to encode math. OMML has no primitive for explicit horizontal spacing, so `\ `, `\,`, `\quad`, and similar LaTeX spacing commands are **silently dropped** during RTF conversion. There is no workaround.
- **Pandoc's MathML writer** (used with `--mathml` and HTML output) correctly represents spacing via `<mspace width="0.333em"/>`, `<mspace width="0.167em"/>`, etc.
- **Word 2016 and later** renders pasted MathML equations natively from CF_HTML.

Therefore, the application writes **only CF_HTML** (registered format name `"HTML Format"`) to the clipboard, containing MathML equations.

The CF_HTML format requires a specific ASCII header with nine-digit byte offsets:

```
Version:0.9\r\n
StartHTML:000000127\r\n
EndHTML:000000450\r\n
StartFragment:000000158\r\n
EndFragment:000000419\r\n
<html><body><!--StartFragment-->…content…<!--EndFragment--></body></html>
```

`_make_cf_html()` computes all four offsets precisely in UTF-8 bytes.

---

### LaTeX Post-Processing Pipeline

Pandoc's LaTeX output from OMML conversion has several systematic quirks that `postprocess.py` corrects:

**Multiline equation groups**

Pandoc sometimes emits each line of a multi-line equation as a separate top-level brace group: `{line1}{line2}{line3}`. The `_unwrap_multiline_groups` pass detects this pattern (distinguished from `\frac{a}{b}` by requiring 3+ groups or groups with substantial content) and converts to `line1 \\ line2 \\ line3`.

**Alignment markers**

After splitting on `\\`, each line is scanned for the leftmost relation operator that is not inside braces. An `&` is inserted before it, turning plain multiline math into `aligned`-ready output:

```
Before:  m - M = -5 + 5\log_{10}d \\  M = m + 5
After:   m - M &= -5 + 5\log_{10}d \\  M &= m + 5
```

**Log subscript**

Pandoc inserts an extra `\ ` before subscripts of function names: `\log\ _{10}` → fixed to `\log_{10}`.

**Bold math variables**

Word marks equation variables as bold-italic via `<m:sty m:val="bi"/>`, which Pandoc translates to `\mathbf{x}`. For single-character variable names this is stripped back to plain `x`.

---

## Project Structure

```
WordClipboard2LaTeX/
├── README.md
├── start.bat              # Windows launcher
├── start.sh               # Linux/macOS launcher
├── .gitignore
│
├── backend/
│   ├── main.py            # FastAPI app, all API endpoints
│   ├── clipboard.py       # Windows clipboard read (pywin32)
│   ├── parser.py          # HTML → DocNode tree
│   ├── converter.py       # Orchestrator: DocNode → {latex, markdown, html}
│   ├── omml_to_latex.py   # OMML XML → LaTeX via Pandoc
│   ├── postprocess.py     # LaTeX cleanup pipeline
│   ├── html_to_latex.py   # HTML formatting → LaTeX
│   ├── html_to_markdown.py# HTML formatting → Markdown
│   ├── html_to_html.py    # HTML cleanup / semantic normalization
│   ├── to_clipboard.py    # Markdown/LaTeX → Word clipboard (CF_HTML)
│   ├── requirements.txt
│   └── tests/
│       ├── test_converter.py
│       ├── test_omml_to_latex.py
│       ├── test_parser.py
│       └── fixtures/
│
└── frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.ts     # Dev server + /api proxy to :8741
    ├── tsconfig.json
    └── src/
        ├── main.tsx       # React entry point
        ├── App.tsx        # Root component, layout, state
        ├── App.css        # All layout and component styles
        ├── index.css      # CSS variables, theme definitions
        ├── api.ts         # Typed fetch wrappers
        └── components/
            ├── ConvertButton.tsx   # Primary conversion trigger
            ├── OutputTabs.tsx      # Markdown | LaTeX | HTML tab switcher
            ├── CodeOutput.tsx      # <pre><code> raw display
            ├── CopyButton.tsx      # Browser clipboard copy with feedback
            ├── Preview.tsx         # KaTeX + Marked live renderer
            └── ToWordPanel.tsx     # Reverse conversion input panel
```

---

## Dependencies

### Backend

| Package | Purpose |
|---|---|
| `fastapi` | HTTP API framework |
| `uvicorn` | ASGI server |
| `pywin32` | Windows clipboard access |
| `beautifulsoup4` | HTML parsing |
| `lxml` | Fast HTML/XML parser backend for BS4 |
| `pandoc` (system) | Math conversion (OMML ↔ LaTeX ↔ MathML) |

### Frontend

| Package | Purpose |
|---|---|
| `react` / `react-dom` | UI framework |
| `katex` | Client-side LaTeX math rendering |
| `marked` | Markdown to HTML conversion |
| `vite` | Build tool and dev server |
| `typescript` | Type safety |
