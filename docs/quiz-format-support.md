# Proposal: Quiz Format Support

**Created:** 2026-06-09
**Status:** Done
**Scope:** `backend/quiz_parser.py` (new), `backend/quiz_to_word.py` (new),
`backend/main.py` (new endpoints), `frontend/src/api.ts` (new functions),
`frontend/src/components/QuizPanel.tsx` (new), `frontend/src/App.tsx` (new tab)

---

## 1. Background

WordClipboard2Latex converts arbitrary Word clipboard HTML to LaTeX/Markdown. A
secondary use case has emerged: converting **structured exam-paper HTML** (with
named paragraph styles) into a specific quiz markdown dialect used by the
astro-dev-id Astro/Prisma site, where the MCP quiz server ingests questions in
that format.

## 2. Current State

`parse_clipboard_html` in `parser.py` is style-agnostic — it produces a flat
list of `DocNode` objects and discards paragraph class information. It handles
OMML math correctly via placeholder extraction + Pandoc. The general conversion
pipeline (`converter.py`) turns those nodes into LaTeX / Markdown / HTML.

There is no support for round-tripping **structured question data** (stem,
options list, answer key, solution body) as a typed model.

## 3. Problem

A Word exam paper uses named paragraph styles to encode question structure:

| Word paragraph class | Meaning            |
|----------------------|--------------------|
| `P-Problem`          | Problem stem       |
| `P-Sub-problem`      | Answer option      |
| `Solution-Title`     | Answer key line    |
| `Solution`           | Solution body      |

The existing pipeline flattens these into undifferentiated paragraphs, losing
the structural information. The output cannot be fed directly to the quiz MCP
server's `quiz_append_from_markdown` or `quiz_import_zip` tools.

## 4. Proposal

Add a **quiz-aware parsing path** as a separate module (`quiz_parser.py`) that:

1. Reuses the existing OMML preprocessing pipeline (unwrap conditionals →
   extract OMML blocks → preserve spacerun indent → BeautifulSoup parse).
2. Walks `<p>` elements, grouping them by their CSS class into `QuizQuestion`
   dataclasses.
3. Strips Word list-label spans (`mso-list:Ignore`) so they don't bleed into
   option text.
4. Converts inline and display OMML math to LaTeX via the existing
   `omml_to_latex` + `postprocess_latex` utilities.
5. Renders the result in one of two formats:
   - **`astro_dev_id`** — the site's quiz markdown dialect
     (`## stem`, `### option`, `<solution_title>`)
   - **`generic`** — plain numbered/lettered MCQ markdown

A new API endpoint (`GET /api/convert/quiz?preset=astro_dev_id`) reads the
clipboard and returns the structured result plus the rendered markdown string.

A new **Quiz tab** in the React frontend surfaces this endpoint with a
structured card preview and a copyable markdown output area.

### Astro-dev-id output format

```
---

## [problem stem]

### [option A text]

### [option B text]

### [option C text]

### [option D text]

### [option E text]

<solution_title> Jawaban: D

[solution body — plain text paragraphs and $$...$$ display math]

---
```

## 5. Reverse direction: Quiz MD → Word

Implemented in `backend/quiz_to_word.py`.  Two output paths:

### 5a. Clipboard (CF_HTML)

- Endpoint: `POST /api/quiz/to-clipboard` — body `{"text": "..."}`
- Builds a CF_HTML blob with `mso-style-name` mappings so Word applies
  existing named styles on paste.
- Math: Pandoc `--mathml` converts `$...$` / `$$...$$` to MathML; Word
  converts MathML → OMML on paste.

**Key implementation details:**

| Issue | Fix |
|---|---|
| Word ignored class names → everything "Normal" | Added `<meta name="ProgId" content="Word.Document">`, `<meta name="Generator" content="Microsoft Word 15">`, and `xmlns:o` / `xmlns:w` to `_HTML_HEAD` |
| `mso-style-name` values didn't match Word style names | Corrected to `"P - Problem"`, `"P - Sub-problem"`, `"Solution - Title"` (spaces around hyphens match internal Word names) |
| Space after inline math lost on paste | `_fix_math_spacing()`: replaces `</math>\s+` with `</math>&#160;` — `&#160;` is an explicit HTML entity, not bare whitespace, so Word preserves it through MathML→OMML conversion |
| "Jawaban" line not bold | Bold declared in the CSS rule for `.Solution-Title` (`font-weight:bold;mso-bidi-font-weight:normal`) — bold comes from paragraph style, not a character `<b>` wrapper |

### 5b. DOCX (Pandoc custom-style fenced divs)

- Endpoint: `POST /api/quiz/to-docx` — body `{"text": "...", "reference_doc": null}`
- Converts quiz markdown to Pandoc fenced-div markdown, runs `pandoc -t docx`.
- Math converts to OMML natively.
- Custom-style names used: `"P - Problem"`, `"P - Sub-problem"`, `"Solution - Title"`, `"Solution"`.
- **Requires** `reference_doc` pointing to a `.docx` template that defines
  those four named paragraph styles.  Without it, Pandoc creates the styles
  from scratch (unstyled but valid DOCX with correct math).

## 6. Known Limitations

- **Decimal commas**: Indonesian math notation `0{,}550` is represented in the
  OMML as a plain comma, which Pandoc outputs as `0,550` (no `{,}` wrapper).
  This is correct LaTeX but differs from the manually written `{,}` style.
- **Solution subheadings**: Bold `**Cara pengerjaan**` headings inside the
  solution body are reproduced as bold text, not as `###` headings, since they
  arrive as `<b>` spans rather than named paragraph styles.
- **DOCX without template**: Without a `reference_doc` template, the DOCX has
  correct content and math but unstyled paragraphs.  The style names are
  embedded and will apply correctly if the document is later associated with or
  copied into a document that defines the styles.
- **Mathpix-style export**: Research ongoing. Mathpix Markdown (`MMD`) is a
  documented format and `mathpix-markdown-it` exists as an npm renderer;
  Pandoc OMML output may provide a sufficient alternative without the Mathpix
  API dependency.

## 7. Implementation Order

1. `backend/quiz_parser.py` — data model + HTML parser + two renderers
2. `backend/main.py` — two new endpoints (`GET` and `POST /api/convert/quiz`)
3. `frontend/src/api.ts` — `convertQuiz` / `convertQuizText` helpers
4. `frontend/src/components/QuizPanel.tsx` — Quiz tab UI
5. `frontend/src/App.tsx` — register the new tab
