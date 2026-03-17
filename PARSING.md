# Word Clipboard Parsing — Implementation Notes

This document explains how `backend/parser.py` converts Word clipboard HTML into
structured document nodes, with detailed notes on the non-obvious custom fixes.

---

## Overview: The Pipeline

```
Windows clipboard (CF_HTML)
        │
        ▼
clipboard.py: read_clipboard_html()
        │  strips CF_HTML header, returns raw HTML string
        ▼
parser.py: parse_clipboard_html()
        │
        ├─ Step 1: _unwrap_omml_conditionals()
        │     Unwrap OMML from Word's IE conditional comments
        │
        ├─ Step 2: _extract_omml_blocks()
        │     Lift <m:oMathPara> / <m:oMath> out of HTML before BS4
        │     touches them; replace with <omml-display id=N> placeholders
        │
        ├─ Step 2b: _preserve_spacerun_indent()
        │     Replace spaces in mso-spacerun spans with ␀ (U+E000) markers
        │
        ├─ Step 3: BeautifulSoup("lxml") parse
        │
        ├─ Step 4: _walk_elements()
        │     Build list[DocNode] from the parsed tree
        │
        └─ Step 5: _group_code_lines()
              Merge consecutive CODE_LINE nodes → fenced code blocks,
              deduplicate Word's double-paste artifacts
        │
        ▼
list[DocNode]  →  converter.py  →  markdown / LaTeX / HTML strings
```

---

## Why BS4/lxml Can't See the Raw HTML Directly

Word clipboard HTML mixes two incompatible XML namespaces in one document:

- **HTML** (`<p>`, `<span>`, `<table>`, …)
- **OMML** (`<m:oMath>`, `<m:sSup>`, `<m:f>`, …) — Office Math Markup Language

BS4's `lxml` parser treats OMML tags as unknown HTML, lowercases them
(`<m:oMath>` → `<m:omath>`), restructures self-closing tags, and reorders
attributes. Pandoc (used to convert OMML → LaTeX) requires the original
casing and structure, so OMML must be extracted **before** BS4 sees the HTML.

---

## Step 1 — Conditional Comment Unwrapping

Word wraps OMML in Internet Explorer conditional comments so that older
browsers show a fallback image instead:

```html
<!--[if gte msEquation 12]>
  <m:oMathPara>…</m:oMathPara>
<![endif]-->
<!--[if !msEquation]>
  <img src="equation.png"/>   ← fallback image
<![endif]-->
<!--[if gte vml 1]>
  <v:shape …/>                ← VML vector fallback
<![endif]-->
```

`_unwrap_omml_conditionals()` applies three regex passes:

1. `_OMML_CONDITIONAL_RE` — matches `[if gte msEquation 12]` blocks, keeps the inner OMML.
2. `_FALLBACK_CONDITIONAL_RE` — matches `[if !msEquation]` blocks, discards them entirely.
3. `_REMAINING_CONDITIONAL_RE` — discards all other conditional comments (VML, etc.).

---

## Step 2 — OMML Placeholder Extraction

After unwrapping conditionals, OMML blocks appear as raw XML in the HTML string.
They are extracted with two regexes:

- `_OMATHPARA_RE` matches `<m:oMathPara>…</m:oMathPara>` → **display math**
- `_OMATH_RE` matches standalone `<m:oMath>…</m:oMath>` → **inline math**

Each match is stored in a dict (`display_blocks` / `inline_blocks`) keyed by a
counter string, and replaced in the HTML with a custom placeholder tag:

```html
<omml-display data-id="0"></omml-display>
<omml-inline data-id="1"></omml-inline>
```

BS4 treats these as ordinary (unknown) HTML tags, preserving their `data-id`
attributes, so `_walk_elements()` can retrieve the original OMML XML by id.

The math environment (`aligned`, `multiline`, `pmatrix`, or plain) is detected
from the raw OMML XML at this stage via `_detect_math_env_from_xml()`, which
looks for `<m:eqArr>` (equation array → aligned), multiple `<m:oMath>` inside
one `<m:oMathPara>` (multiline), and `<m:m>` (matrix → pmatrix).

---

## Step 2b — Code Indentation: The mso-spacerun Fix

### The Problem

Word encodes leading indentation in code blocks using a special `mso-spacerun:yes`
span attribute:

```html
<span style='mso-spacerun:yes'>    </span>"email": "user@example.com"
```

The span content is 4 spaces (or non-breaking spaces `\xa0`) — one per indent level.

lxml's HTML parser normalises whitespace inside inline elements, collapsing or
dropping these spaces entirely before any Python code can count them. By the time
`p_tag.get_text()` is called, the indentation is gone.

### The Fix: Private-Use Marker (U+E000)

**Before** passing the HTML to BS4, `_preserve_spacerun_indent()` runs a regex
substitution over the raw HTML string, replacing each space or `\xa0` inside
`mso-spacerun` spans with the Unicode Private Use Area character `\ue000`
(chosen because lxml never strips PUA characters, and Word documents never
contain them legitimately):

```python
_SPACERUN_RE = re.compile(
    r'(<span[^>]+mso-spacerun[^>]*>)([ \t\n\r\xa0]*)(</span>)',
    re.IGNORECASE | re.DOTALL,
)

def replace(m):
    spaces = sum(1 for c in m.group(2) if c in (' ', '\xa0'))
    return m.group(1) + ('\ue000' * spaces) + m.group(3)
```

Key design decisions:

| Decision | Reason |
|---|---|
| `[^>]+` in regex (not `[^\n>]`) | Word often emits `<span\nstyle='mso-spacerun:yes'>` with a newline inside the tag — `[^>]` matches newlines, `[^\n>]` would not |
| Count `\xa0` as one space | Word uses non-breaking space (`\xa0` / `&nbsp;`) for indentation, not regular ASCII space |
| Ignore `\n\r\t` in the content | These are HTML source formatting, not indentation characters |
| `re.DOTALL` on the whole pattern | Allows `.` in `[^>]*` to span the embedded newline in the tag |

After BS4 parsing, `_extract_code_line_text()` counts leading `\ue000` characters
to reconstruct the original indentation:

```python
raw = p_tag.get_text().strip('\n\r')
if '\ue000' in raw:
    trimmed = raw.lstrip(' \t')          # strip any lxml-added whitespace first
    inner   = trimmed.lstrip('\ue000')   # strip markers
    leading = len(trimmed) - len(inner)  # number of markers = number of spaces
else:
    # Fallback: no markers (regex didn't fire), count real leading spaces
    inner   = raw.lstrip(' \t')
    leading = len(raw) - len(inner)

content = re.sub(r'\s+', ' ', inner.lstrip()).strip()
return ' ' * leading + content
```

---

## Step 4 — Tree Walking and Node Classification

`_walk_elements()` visits every child of `<body>` and dispatches by tag:

| HTML element | Action |
|---|---|
| `<omml-display>` | Look up OMML XML by `data-id`, emit `DISPLAY_MATH` node |
| `<omml-inline>` | Same, emit `INLINE_MATH` node |
| `<table>` | `_handle_table()` → `TABLE` node |
| `<ul>` / `<ol>` | `_handle_list()` → `TEXT` node with Markdown list syntax |
| `<pre>` | Emit `TEXT` node with fenced code block directly |
| `<p>` | `_handle_paragraph()` — most of the logic lives here |
| `<h1>`–`<h6>` or `MsoHeadingN` class | `HEADING` node |
| anything else | Recurse into children |

### Paragraph Classification (`_handle_paragraph`)

Each `<p>` is classified in priority order:

1. **Display math**: contains `<omml-display>` → `DISPLAY_MATH` node
2. **Heading**: has `MsoHeadingN` CSS class → `HEADING` node
3. **List item**: has `mso-list:lN levelM` in style → `_handle_list_item_para()`
4. **Code line**: `_is_monospace_paragraph()` returns True → `CODE_LINE` node
5. **Mixed/regular**: `_extract_inline()` to collect text + inline math children

---

## Custom Fix: Monospace Paragraph Detection

`_is_monospace_paragraph()` classifies an entire `<p>` as a code line only when
**all** non-whitespace text content is inside monospace-font spans (Courier New,
Consolas, Monaco, etc.):

```python
has_monospace_text    = False  # at least one monospace span with text
has_non_monospace_text = False  # any text NOT in a monospace span
has_spacerun_indent   = False  # a pure-indent mso-spacerun span (markers only)
```

The function iterates the **direct children** of `<p>` (not all descendants) and
classifies each:

- **Bare `NavigableString`** directly inside `<p>`: non-monospace text
- **`mso-spacerun` span** whose content is only `\ue000` markers: indent-only, not text
- **`o:p`, `w:bookmarkstart`, `w:bookmarkend`**: Word field tags, ignored
- **Span with `font-family` in a monospace font list**: monospace text
- **Anything else with visible text**: non-monospace text

Result:
- `has_non_monospace_text = True` → return `False` (mixed paragraph; use inline backtick logic)
- `has_monospace_text OR has_spacerun_indent` → return `True` (code line)

This ensures that a sentence like *"Use the `brokerageUrl` field"* — where only
the field name is in Courier New — is NOT treated as a code block, but instead
gets inline backticks via `_extract_inline()`.

---

## Custom Fix: Inline Backtick Detection

For **mixed paragraphs** (regular text containing monospace spans), `_extract_inline()`
wraps each monospace span in backticks:

```python
elif tag_name == "span" and _span_is_monospace(child):
    text = child.get_text().strip()
    if text:
        out.append(DocNode(type=NodeType.TEXT, content=f"`{text}`", html=""))
```

The same logic applies inside list items via `_li_text_with_code()`, which
recursively visits list-item children and wraps monospace spans.

---

## Step 5 — Code Block Grouping and Deduplication

`_group_code_lines()` processes the flat `CODE_LINE` list in two passes.

**Pass 1 — Grouping:** Consecutive `CODE_LINE` nodes are merged into a single
`('code', [lines…])` entry, interspersed with `('node', DocNode)` entries.

**Pass 2 — Deduplication:** Word/Slack sometimes pastes code twice — once in the
document's default font (which produces `TEXT` nodes for outer braces like `{` and
`}`) and once in Courier New (a complete `CODE_LINE` run). The result is a code
block that is a **superset** of an earlier block whose outer lines appear as
orphan `TEXT` nodes.

Detection: for every pair of code blocks `(i, j)` where `i < j`, if the stripped
line-set of block `i` is a **subset** of block `j`, block `i` is marked for
removal. Additionally, any `TEXT` node between `i` and `j` whose content appears
as a line in block `j` is also removed (the orphaned outer braces).

The final code block is emitted as a `TEXT` node:

```
``` (backtick-fenced)
line1
    line2
        line3
```

---

## Equation Conversion: OMML → LaTeX

`omml_to_latex.py` converts OMML XML to LaTeX by embedding it in a minimal `.docx`
archive and running **Pandoc**:

```
OMML XML
  → wrap in minimal document.xml
  → zip into in-memory .docx
  → pandoc --from docx --to latex
  → extract math from \[ … \] or $ … $
  → postprocess_latex()
```

The `.docx` is built in memory (no temp file write) as a `zipfile.ZipFile` in a
`BytesIO` buffer, keeping latency low.

### postprocess_latex() — Space-Preserving Fixes

Pandoc's LaTeX output requires several corrections:

| Fix | Problem | Solution |
|---|---|---|
| `_unwrap_multiline_groups` | Pandoc wraps each line of a multi-equation block in `{…}` braces | Detect consecutive top-level brace groups, join with `\\` |
| `_unwrap_array_in_aligned` | Pandoc uses `\begin{array}{r}…\end{array}` inside aligned | Strip the array wrapper, keep rows |
| `_collapse_nested_aligned` | Pandoc sometimes nests `aligned` inside `aligned` | Remove the outer shell |
| `_add_alignment_markers` | Multi-line equations need `&` before `=` / `\approx` / etc. for `aligned` env | Find first relation operator on each `\\`-separated line, not inside braces, insert `&` |
| `_fix_bold_math_vars` | Word marks equation variables as bold-italic; Pandoc produces `\mathbf{x}` | Strip `\mathbf{}` for single-letter variables |
| `_fix_log_subscript` | Pandoc emits `\log\ _{10}` (extra backslash-space) | Regex: `\log\ _{` → `\log_{` |
| `_fix_number_unit_spacing` | `5407 \text{Å}` — spaces are ignored in math mode | Insert `\,` between a digit and `\text{…}` |
| `_fix_common_pandoc_quirks` | `\text{ }`, empty `{}`, `\\\\`, `\left ` spacing | Various targeted regexes |

The alignment marker insertion (`_insert_alignment`) walks each line character by
character tracking brace depth, so it skips operators inside `\frac{…}{…}`
argument braces and only fires on top-level operators.

---

## Word HTML Quirks Reference

| Quirk | What Word does | How we handle it |
|---|---|---|
| Indentation in code | `<span style='mso-spacerun:yes'>\xa0\xa0\xa0 </span>` | `_preserve_spacerun_indent` → `\ue000` markers |
| Equations wrapped in IE comments | `<!--[if gte msEquation 12]>…<![endif]-->` | `_unwrap_omml_conditionals` |
| VML / image equation fallbacks | `<!--[if gte vml 1]>…<![endif]-->` | Stripped in same pass |
| Lists as `<p>` with CSS | `mso-list:l0 level1` in paragraph style | `_get_list_level` + `_handle_list_item_para` |
| Heading via CSS class | `class="MsoHeading1"` not `<h1>` | `HEADING_RE` regex on class name |
| Bullet glyphs in Symbol font | `<span style="font-family:Symbol">·</span>` | Skipped in `_handle_list_item_para` |
| Code pasted twice | Default font + Courier New copy | Subset deduplication in `_group_code_lines` |
| Inline code in sentences | Courier New span inside normal paragraph | `_extract_inline` → backtick wrap |
