"""Parse Word clipboard HTML with quiz paragraph styles into quiz markdown.

Reuses the OMML preprocessing pipeline from parser.py but walks <p> elements
by CSS class, grouping them into typed QuizQuestion objects.

Supported presets
-----------------
astro_dev_id  — astro-dev-id site format:
                  ## stem, ### option, <solution_title> Jawaban: X
generic       — plain numbered/lettered MCQ markdown
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, NavigableString, Tag

from omml_to_latex import omml_to_latex
from parser import (
    _INDENT_MARKER,
    _detect_math_env_from_xml,
    _extract_omml_blocks,
    _preserve_spacerun_indent,
    _unwrap_omml_conditionals,
)
from postprocess import postprocess_latex


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class QuizQuestion:
    number: int = 0
    qtype: str = "mc"          # "mc" | "cmc" | "fitb" | "essay"
    stem: str = ""
    options: list[str] = field(default_factory=list)
    answer_label: str = ""     # "A" … "E" — single MC (kept for back-compat)
    answer_labels: list[str] = field(default_factory=list)  # CMC: ["A", "C"]
    subparts: list[str] = field(default_factory=list)       # essay "### Part N:" headers
    blanks: list[str] = field(default_factory=list)         # FITB "### Jawaban N: …" bodies
    meta: str = ""             # raw BANK_META / meta comment body (verbatim)
    solution_body: str = ""

    @property
    def answer_spec(self) -> str:
        """The text after 'Jawaban:' / 'Solusi' for the Solution-Title line."""
        if self.qtype == "essay":
            return "Solusi"
        if self.qtype == "fitb":
            return "Jawaban: Isian"
        if self.qtype == "cmc":
            return "Jawaban: " + ", ".join(self.answer_labels)
        return f"Jawaban: {self.answer_label}"


@dataclass
class QuizParseResult:
    questions: list[QuizQuestion] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CSS class detection
# ---------------------------------------------------------------------------

_QUIZ_CLASSES = frozenset({
    "P-Problem", "P-Sub-problem", "Solution-Title", "Solution",
    "Blank-Key", "Problem-Meta",
})


def _get_para_class(p_tag: Tag) -> str | None:
    """Return the quiz-relevant CSS class of a <p> tag, or None."""
    classes = p_tag.get("class", [])
    if isinstance(classes, str):
        classes = classes.split()
    for c in classes:
        if c in _QUIZ_CLASSES:
            return c
    return None


# ---------------------------------------------------------------------------
# Inline content extraction
# ---------------------------------------------------------------------------

def _convert_omml(xml: str, warnings: list[str]) -> str:
    """OMML XML → bare LaTeX string (no delimiters)."""
    try:
        raw = omml_to_latex(xml)
        return postprocess_latex(raw).strip()
    except Exception as e:
        warnings.append(f"Math conversion error: {e}")
        return ""


def _should_skip(tag: Tag) -> bool:
    """Return True for Word list-label, indentation, and bullet spans."""
    style = tag.get("style", "").lower().replace(" ", "")
    if "mso-list:ignore" in style:
        return True
    if "mso-spacerun" in style:
        return True
    if "font-family:symbol" in style:
        return True
    return False


def _extract_inline_md(tag: Tag, inline_blocks: dict[str, str], warnings: list[str]) -> str:
    """Recursively extract inline content as markdown with LaTeX math."""
    parts: list[str] = []

    for child in tag.children:
        if isinstance(child, NavigableString):
            text = str(child).replace(_INDENT_MARKER, "").strip("\n\r")
            text = re.sub(r"\s+", " ", text)
            if text.strip():
                parts.append(text)
            continue

        if not isinstance(child, Tag):
            continue

        name = (child.name or "").lower()

        if name == "omml-inline":
            block_id = child.get("data-id", "")
            xml = inline_blocks.get(block_id, "")
            if xml:
                latex = _convert_omml(xml, warnings)
                if latex:
                    parts.append(f"${latex}$")
            continue

        # Skip list labels, indentation noise, bullet glyphs
        if _should_skip(child):
            continue

        # Skip Word field tags that carry no visible text
        if name in ("o:p",):
            continue

        if name in ("b", "strong"):
            inner = _extract_inline_md(child, inline_blocks, warnings).strip()
            if inner:
                parts.append(f"**{inner}**")
            continue

        if name in ("i", "em"):
            inner = _extract_inline_md(child, inline_blocks, warnings).strip()
            if inner:
                parts.append(f"*{inner}*")
            continue

        # Recurse into everything else: font, span, div, a, etc.
        inner = _extract_inline_md(child, inline_blocks, warnings)
        if inner:
            parts.append(inner)

    result = "".join(parts)
    # Collapse runs of whitespace that accumulate from nested tag boundaries
    return re.sub(r" {2,}", " ", result)


def _extract_solution_para(
    p_tag: Tag,
    display_blocks: dict[str, str],
    inline_blocks: dict[str, str],
    warnings: list[str],
) -> str:
    """Extract a Solution paragraph as markdown, handling display math blocks."""
    display_ph = p_tag.find("omml-display")
    if display_ph:
        block_id = display_ph.get("data-id", "")
        xml = display_blocks.get(block_id, "")
        if xml:
            math_env = _detect_math_env_from_xml(xml)
            latex = _convert_omml(xml, warnings)
            if math_env in ("aligned", "multiline"):
                return f"$$\n\\begin{{aligned}}\n{latex}\n\\end{{aligned}}\n$$"
            return f"$$\n{latex}\n$$"
        return ""

    return _extract_inline_md(p_tag, inline_blocks, warnings).strip()


# ---------------------------------------------------------------------------
# Answer-label extraction
# ---------------------------------------------------------------------------

def _classify_answer_line(raw: str) -> tuple[str, list[str]]:
    """Classify a Solution-Title line into (qtype, answer_labels).

    Mirrors quiz-markdown-v2.ts:
      'Jawaban: C'        -> ("mc",    ["C"])
      'Jawaban: A, C'     -> ("cmc",   ["A", "C"])
      'Jawaban: Isian'    -> ("fitb",  [])
      'Solusi' / 'Essay'  -> ("essay", [])
    """
    # Strip the leading label ("Jawaban:", "Answer:", "Kunci Jawaban:", "Solusi").
    m = re.search(
        r"(?:Jawaban|Kunci\s*Jawaban|Answer|Solusi)\s*[:\-]?\s*(.*)$",
        raw, re.IGNORECASE,
    )
    spec = (m.group(1) if m else raw).strip()
    norm = spec.lower()

    if re.search(r"\bsolusi\b", raw, re.IGNORECASE) and not spec:
        return "essay", []
    if norm in ("essay", "uraian", ""):
        # Bare "Solusi" (spec empty) is essay; an empty non-Solusi line is essay too.
        return "essay", []
    if norm == "isian":
        return "fitb", []

    letters = [t.strip(".,;:").upper() for t in re.split(r"[,\s]+", spec) if t.strip(".,;:")]
    letters = [l for l in letters if re.match(r"^[A-E]$", l)]
    if not letters:
        return "essay", []
    if len(letters) == 1:
        return "mc", letters
    return "cmc", letters


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_quiz_clipboard(html: str) -> QuizParseResult:
    """Parse Word clipboard HTML with quiz styles into a QuizParseResult."""
    result = QuizParseResult()

    # Shared preprocessing — identical to parse_clipboard_html in parser.py
    html = _unwrap_omml_conditionals(html)
    html, display_blocks, inline_blocks = _extract_omml_blocks(html)
    html = _preserve_spacerun_indent(html)

    soup = BeautifulSoup(html, "lxml")

    current: QuizQuestion | None = None
    q_number = 0

    for p in soup.find_all("p"):
        cls = _get_para_class(p)
        if cls is None:
            continue

        if cls == "P-Problem":
            if current is not None:
                result.questions.append(current)
            q_number += 1
            current = QuizQuestion(number=q_number)
            current.stem = _extract_inline_md(p, inline_blocks, result.warnings).strip()

        elif cls == "P-Sub-problem":
            if current is None:
                result.warnings.append("P-Sub-problem found before any P-Problem; skipping.")
                continue
            text = _extract_inline_md(p, inline_blocks, result.warnings).strip()
            if text:
                current.options.append(text)

        elif cls == "Blank-Key":
            if current is None:
                continue
            text = _extract_inline_md(p, inline_blocks, result.warnings).strip()
            if text:
                current.qtype = "fitb"
                current.blanks.append(text)

        elif cls == "Problem-Meta":
            if current is None:
                continue
            text = _extract_inline_md(p, inline_blocks, result.warnings).strip()
            if text:
                current.meta = text

        elif cls == "Solution-Title":
            if current is None:
                continue
            raw = p.get_text(strip=True)
            qtype, labels = _classify_answer_line(raw)
            # Blank-Key paragraphs may have already fixed qtype to "fitb".
            if current.qtype != "fitb":
                current.qtype = qtype
            current.answer_labels = labels
            current.answer_label = labels[0] if labels else ""

        elif cls == "Solution":
            if current is None:
                continue
            text = _extract_solution_para(p, display_blocks, inline_blocks, result.warnings).strip()
            if text:
                sep = "\n\n" if current.solution_body else ""
                current.solution_body += sep + text

    if current is not None:
        result.questions.append(current)

    if not result.questions:
        result.warnings.append(
            "No quiz paragraphs found. "
            "Expected Word paragraph styles: P-Problem, P-Sub-problem, "
            "Solution-Title, Solution."
        )

    return result


# ---------------------------------------------------------------------------
# Quiz markdown → QuizQuestion (reverse direction)
# ---------------------------------------------------------------------------

_META_JSON_RE = re.compile(r"<!--\s*BANK_META:\s*(\{[\s\S]*?\})\s*-->", re.IGNORECASE)
_META_KV_RE = re.compile(r"<!--\s*meta\s*\n([\s\S]*?)-->", re.IGNORECASE)
_COMMENT_RE = re.compile(r"<!--[\s\S]*?-->")
_BLANK_KEY_RE = re.compile(r"(?im)^###\s*Jawaban\s*\d+:.*$")


def _extract_meta(block: str) -> str:
    """Return the inner text of a BANK_META / meta comment, or '' if none.

    Mirrors bank-meta.ts: JSON form is preferred, key/value form is the
    fallback.  The returned string is the *inner* payload (no ``<!-- -->``),
    ready to render into a Problem-Meta paragraph and re-wrap on the way back.
    """
    m = _META_JSON_RE.search(block)
    if m:
        return f"BANK_META: {m.group(1).strip()}"
    m = _META_KV_RE.search(block)
    if m:
        return "meta\n" + m.group(1).strip()
    return ""


def parse_quiz_md(text: str) -> list[QuizQuestion]:
    """Parse astro-dev-id quiz markdown into QuizQuestion list.

    Auto-detects the grammar and normalizes both into the same QuizQuestion
    shape so every renderer (Word clipboard, DOCX, reverse markdown) is
    format-agnostic:

      * ``<solution_title>`` present  → v2 (mirrors quiz-markdown-v2.ts)
      * otherwise                     → v3 Unified Problem Markdown
        (mirrors quiz-markdown-v3.ts: ``- (A)`` options, ``### Jawaban`` /
        ``### Pembahasan`` sections, ```` ```meta ```` fence, ``{{N}}`` blanks).
    """
    if "<solution_title>" in text.lower():
        return _parse_quiz_md_v2(text)
    return _parse_quiz_md_v3(text)


def _parse_quiz_md_v2(text: str) -> list[QuizQuestion]:
    """v2 (`<solution_title>`) → QuizQuestion. Split on ``^## ``; type from the marker."""
    body = re.sub(r"^---[\s\S]*?---\s*\n?", "", text)   # strip YAML front-matter
    blocks = re.split(r"(?m)^## ", body)
    questions: list[QuizQuestion] = []
    number = 0

    for block in blocks:
        if "<solution_title>" not in block.lower():
            continue
        q = _parse_quiz_block(block)
        if q is not None:
            number += 1
            q.number = number
            questions.append(q)

    return questions


# ── v3 (Unified Problem Markdown) → QuizQuestion ──────────────────────────────

_V3_META_FENCE_RE = re.compile(r"```meta[ \t]*\n(.*?)```", re.IGNORECASE | re.DOTALL)
_V3_ANSWER_LABEL_RE = re.compile(r"^(jawaban|answer|kunci)\b", re.IGNORECASE)
_V3_SOLUTION_LABEL_RE = re.compile(r"^(pembahasan|solusi|penyelesaian|solution)\b", re.IGNORECASE)
_V3_OPTION_RE = re.compile(r"^-\s*\(([A-Za-z])\)\s+(.+)$")
_V3_OPTION_LEGACY_RE = re.compile(r"^([A-Ea-e])[.)]\s+(.+)$")
_V3_BLANK_MARKER_RE = re.compile(r"\{\{\s*\d+\s*\}\}")


def _v3_parse_scalar(raw: str):
    v = raw.strip()
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    if re.match(r"^-?\d+$", v):
        return int(v)
    if re.match(r"^-?\d*\.\d+$", v):
        return float(v)
    if v == "true":
        return True
    if v == "false":
        return False
    return v


def _v3_parse_inline(raw: str):
    v = raw.strip()
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [_v3_parse_scalar(s) for s in inner.split(",")] if inner else []
    if v.startswith("{") and v.endswith("}"):
        inner = v[1:-1].strip()
        out = {}
        if inner:
            for pair in inner.split(","):
                if ":" in pair:
                    k, val = pair.split(":", 1)
                    out[k.strip()] = _v3_parse_scalar(val)
        return out
    return _v3_parse_scalar(v)


def _v3_parse_meta_yaml(text: str) -> dict:
    """Minimal YAML subset for the ```meta fence (mirrors quiz-markdown-v3.ts)."""
    root: dict = {}
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        raw = lines[i]
        if not raw.strip() or raw.strip().startswith("#"):
            i += 1
            continue
        if len(raw) - len(raw.lstrip()) > 0:   # indented child, handled by parent
            i += 1
            continue
        m = re.match(r"^([\w-]+):\s*(.*)$", raw.strip())
        if not m:
            i += 1
            continue
        key, rest = m.group(1), m.group(2)
        if rest == "":
            child = []
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip()) > 0):
                if lines[j].strip():
                    child.append(lines[j].strip())
                j += 1
            if child and all(c.startswith("- ") for c in child):
                root[key] = [_v3_parse_scalar(c[2:]) for c in child]
            else:
                mp = {}
                for c in child:
                    mm = re.match(r"^([\w-]+):\s*(.*)$", c)
                    if mm:
                        mp[mm.group(1)] = _v3_parse_scalar(mm.group(2))
                root[key] = mp
            i = j
        else:
            root[key] = _v3_parse_inline(rest)
            i += 1
    return root


def _v3_topic_obj(t):
    """"Topic/Subtopic" string → {topic, subtopic}; pass dicts through."""
    if isinstance(t, str):
        parts = [p.strip() for p in t.split("/")]
        return {"topic": parts[0], "subtopic": parts[1]} if len(parts) > 1 else {"topic": parts[0]}
    return t


def _parse_quiz_md_v3(text: str) -> list[QuizQuestion]:
    body = re.sub(r"^---[\s\S]*?---\s*\n?", "", text)   # strip YAML front-matter
    blocks = re.split(r"(?m)^## ", body)
    questions: list[QuizQuestion] = []
    number = 0

    for raw in blocks:
        if not raw.strip():
            continue
        q = _parse_quiz_block_v3(raw)
        if q is not None:
            number += 1
            q.number = number
            questions.append(q)

    return questions


def _parse_quiz_block_v3(block: str) -> QuizQuestion | None:
    q = QuizQuestion()

    # Pull the ```meta fence out first so its `- ` topic lines aren't read as
    # options. Canonicalize to single-line BANK_META JSON — the only form that
    # survives Word's paragraph model (multi-line YAML collapses on paste).
    fence = _V3_META_FENCE_RE.search(block)
    type_override = ""
    if fence:
        obj = _v3_parse_meta_yaml(fence.group(1))
        if obj.get("type"):
            type_override = str(obj.pop("type")).lower()
        if isinstance(obj.get("topics"), list):
            obj["topics"] = [_v3_topic_obj(t) for t in obj["topics"]]
        q.meta = "BANK_META: " + json.dumps(obj, ensure_ascii=False) if obj else ""
        block = _V3_META_FENCE_RE.sub("", block)

    # Split into head (stem + options) and ### sections.
    marks = list(re.finditer(r"(?m)^###[ \t]+(.+?)[ \t]*$", block))
    head = block[: marks[0].start()] if marks else block
    sections = []
    for i, mk in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(block)
        sections.append((mk.group(1), block[mk.end():end].strip()))

    # Separate stem lines from option lines in the head.
    stem_lines, options = [], []
    for line in head.split("\n"):
        om = _V3_OPTION_RE.match(line) or _V3_OPTION_LEGACY_RE.match(line)
        if om:
            options.append((om.group(1).upper(), om.group(2).strip()))
        else:
            stem_lines.append(line)
    options.sort(key=lambda o: o[0])
    q.stem = "\n".join(stem_lines).strip()
    q.options = [text for _, text in options]

    answer = next((body for label, body in sections if _V3_ANSWER_LABEL_RE.match(label)), None)
    solution = next((body for label, body in sections if _V3_SOLUTION_LABEL_RE.match(label)), None)
    q.solution_body = (solution or "").strip()

    # Type resolution (mirrors quiz-markdown-v3.ts §4.6).
    has_blanks = bool(_V3_BLANK_MARKER_RE.search(q.stem)) or bool(re.search(r"_{3,}", q.stem))
    answer_numbered = bool(answer and re.search(r"(?m)^\s*\d+\.\s", answer))
    if type_override in ("multiple-choice", "complex-multiple-choice", "fill-in-the-blank", "essay"):
        q.qtype = {"multiple-choice": "mc", "complex-multiple-choice": "cmc",
                   "fill-in-the-blank": "fitb", "essay": "essay"}[type_override]
    elif has_blanks or answer_numbered:
        q.qtype = "fitb"
    elif answer is not None:
        letters = _v3_letters(answer)
        q.qtype = "cmc" if len(letters) >= 2 else "mc"
    else:
        q.qtype = "essay"

    if q.qtype == "fitb":
        # Store blanks in the v2 "Jawaban N: spec" form so existing renderers work.
        for m in re.finditer(r"(?m)^\s*(\d+)\.\s*(.+)$", answer or ""):
            q.blanks.append(f"Jawaban {m.group(1)}: {m.group(2).strip()}")
    elif q.qtype in ("mc", "cmc"):
        letters = _v3_letters(answer or "")
        q.answer_labels = letters
        q.answer_label = letters[0] if letters else ""

    if not q.stem and not q.options:
        return None
    return q


def _v3_letters(body: str) -> list[str]:
    return [t.strip(".,;: ").upper() for t in re.split(r"[,\s]+", body)
            if re.match(r"^[A-Ea-e]$", t.strip(".,;: "))]


def _parse_quiz_block(block: str) -> QuizQuestion | None:
    """Parse one ``## `` block (leading ``## `` already stripped)."""
    idx = re.search(r"<solution_title>", block, re.IGNORECASE)
    if idx is None:
        return None

    before = block[: idx.start()]
    after = block[idx.start():]

    q = QuizQuestion()
    q.meta = _extract_meta(block)

    # Stem = everything before the first ### (options/subparts) or marker,
    # with comments stripped.  Full stem (incl. ### subparts) is kept for essay.
    stem_full = _COMMENT_RE.sub("", before).strip()
    stem_head = re.split(r"(?m)^### ", stem_full)[0].strip()

    # ### lines that appear *before* the marker.
    pre_marker_hashes = [
        ln[4:].strip()
        for ln in _COMMENT_RE.sub("", before).split("\n")
        if ln.startswith("### ")
    ]

    # Classify from the marker line.
    header = re.search(r"<solution_title>\s*Jawaban:\s*([^\n]+)", after, re.IGNORECASE)
    solusi = None if header else re.search(r"<solution_title>\s*Solusi\s*:?", after, re.IGNORECASE)
    if not header and not solusi:
        return None

    spec = header.group(1).strip() if header else ""
    norm = spec.lower()
    if solusi or norm in ("essay", "uraian"):
        q.qtype = "essay"
    elif norm == "isian":
        q.qtype = "fitb"
    elif "," in spec:
        q.qtype = "cmc"
    else:
        q.qtype = "mc"

    # Solution body = text after the marker line, minus meta and (for fitb)
    # the blank-key lines.
    body_match = re.search(r"<solution_title>[^\n]*\n([\s\S]*)", after, re.IGNORECASE)
    sol_raw = body_match.group(1) if body_match else ""

    if q.qtype == "essay":
        q.stem = stem_head
        q.subparts = pre_marker_hashes
        q.solution_body = _strip_meta(sol_raw).strip()

    elif q.qtype == "fitb":
        # Keep the stem verbatim (underscore blanks intact) so re-rendered
        # markdown re-imports cleanly; the DB parser owns the ___ → [[N]] step.
        q.stem = stem_head
        q.blanks = [m.group(0)[4:].strip() for m in _BLANK_KEY_RE.finditer(sol_raw)]
        q.solution_body = _strip_meta(_BLANK_KEY_RE.sub("", sol_raw)).strip()

    else:  # mc / cmc
        q.stem = stem_head
        q.options = pre_marker_hashes
        letters = [l.strip().upper() for l in spec.split(",") if l.strip()]
        q.answer_labels = letters
        q.answer_label = letters[0] if letters else ""
        q.solution_body = _strip_meta(re.sub(r"(?m)^###[^\n]*", "", sol_raw)).strip()

    if not q.stem and not q.options and not q.subparts:
        return None
    return q


def _strip_meta(text: str) -> str:
    """Remove BANK_META / meta comments from a body string."""
    return _META_JSON_RE.sub("", _META_KV_RE.sub("", text))


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

_OPTION_LETTERS = "ABCDE"


def render_astro_dev_id(result: QuizParseResult) -> str:
    """Render questions as astro-dev-id quiz markdown (spec-compliant).

    Emits the DB-contract format (no ``---`` delimiters): ``## stem``,
    ``### option``/``### subpart``, an optional ``<!-- BANK_META … -->`` line,
    ``<solution_title> …``, ``### Jawaban N:`` blank keys for fitb, then the
    solution body.
    """
    blocks: list[str] = []

    for q in result.questions:
        parts: list[str] = [f"## {q.stem}"]

        # ### lines that live *before* the marker: options (mc/cmc) or
        # subparts (essay).  Only one of the two lists is ever populated.
        for opt in q.options:
            parts.append(f"### {opt}")
        for sub in q.subparts:
            parts.append(f"### {sub}")

        if q.meta:
            parts.append(f"<!-- {q.meta} -->")

        spec = "Solusi:" if q.qtype == "essay" else q.answer_spec
        parts.append(f"<solution_title> {spec}")

        # fitb blank keys live *after* the marker.
        for b in q.blanks:
            parts.append(f"### {b}")

        if q.solution_body:
            parts.append(q.solution_body)

        blocks.append("\n\n".join(parts))

    if not blocks:
        return ""
    return "\n\n".join(blocks) + "\n"


def _meta_to_yaml(meta: str) -> str:
    """Best-effort conversion of a QuizQuestion.meta into ```meta YAML body."""
    if not meta:
        return ""
    low = meta.lower()
    if low.startswith("bank_meta:"):
        import json
        try:
            obj = json.loads(meta.split(":", 1)[1].strip())
        except Exception:
            return ""
        lines: list[str] = []
        for key in ("cognitive", "difficulty", "quality", "qualityNote"):
            if obj.get(key) not in (None, ""):
                lines.append(f"{key}: {obj[key]}")
        if isinstance(obj.get("qualityIssues"), list) and obj["qualityIssues"]:
            lines.append("qualityIssues: [" + ", ".join(map(str, obj["qualityIssues"])) + "]")
        if isinstance(obj.get("topics"), list) and obj["topics"]:
            lines.append("topics:")
            for t in obj["topics"]:
                if isinstance(t, dict):
                    name = t.get("topic", "")
                    if t.get("subtopic"):
                        name = f"{name}/{t['subtopic']}"
                    lines.append(f"  - {name}")
                else:
                    lines.append(f"  - {t}")
        if isinstance(obj.get("source"), dict):
            lines.append("source:")
            for k, v in obj["source"].items():
                if v not in (None, ""):
                    lines.append(f"  {k}: {v}")
        return "\n".join(lines)
    if low.startswith("meta"):
        # legacy `meta\n key: value` form — drop the leading `meta` line
        return "\n".join(l.strip() for l in meta.split("\n")[1:] if l.strip())
    return meta  # already YAML (v3 origin)


def render_unified_v3(result: QuizParseResult) -> str:
    """Render questions as v3 Unified Problem Markdown (mirrors quiz-markdown-v3.ts)."""
    blocks: list[str] = []

    for q in result.questions:
        parts: list[str] = []

        if q.qtype == "fitb":
            counter = [0]
            def _blank(_m):
                counter[0] += 1
                return "{{" + str(counter[0]) + "}}"
            parts.append("## " + re.sub(r"_{3,}", _blank, q.stem))
            keys: list[str] = []
            for b in q.blanks:
                m = re.match(r"Jawaban\s*(\d+):\s*(.+)", b)
                keys.append(f"{m.group(1)}. {m.group(2).strip()}" if m else b)
            if keys:
                parts.append("### Jawaban\n" + "\n".join(keys))
        elif q.qtype == "essay":
            parts.append(f"## {q.stem}")
        else:
            parts.append(f"## {q.stem}")
            opts = [f"- ({chr(65 + i)}) {o}" for i, o in enumerate(q.options)]
            if opts:
                parts.append("\n".join(opts))
            if q.qtype == "cmc":
                parts.append("### Jawaban\n" + ", ".join(q.answer_labels))
            else:
                parts.append("### Jawaban\n" + (q.answer_label or "A"))

        if q.solution_body:
            parts.append("### Pembahasan\n" + q.solution_body)

        meta_yaml = _meta_to_yaml(q.meta)
        if meta_yaml:
            parts.append("```meta\n" + meta_yaml + "\n```")

        blocks.append("\n\n".join(parts))

    if not blocks:
        return ""
    return "\n\n".join(blocks) + "\n"


def render_generic(result: QuizParseResult) -> str:
    """Render questions as generic numbered MCQ markdown."""
    lines: list[str] = []

    for q in result.questions:
        lines.append(f"**{q.number}.** {q.stem}")
        lines.append("")
        for i, opt in enumerate(q.options):
            letter = _OPTION_LETTERS[i] if i < len(_OPTION_LETTERS) else str(i + 1)
            lines.append(f"{letter}. {opt}")
        lines.append("")
        if q.answer_label:
            lines.append(f"**Jawaban: {q.answer_label}**")
        if q.solution_body:
            lines.append("")
            lines.append(q.solution_body)
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines).strip()
