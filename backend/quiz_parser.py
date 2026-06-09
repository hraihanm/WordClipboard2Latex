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
    stem: str = ""
    options: list[str] = field(default_factory=list)
    answer_label: str = ""     # "A" … "E" parsed from Solution-Title
    solution_body: str = ""


@dataclass
class QuizParseResult:
    questions: list[QuizQuestion] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CSS class detection
# ---------------------------------------------------------------------------

_QUIZ_CLASSES = frozenset({"P-Problem", "P-Sub-problem", "Solution-Title", "Solution"})


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

def _parse_answer_label(raw: str) -> str:
    """Extract 'D' from 'Jawaban: D', 'Answer: D', etc."""
    m = re.search(r"(?:Jawaban|Kunci\s*Jawaban|Answer)\s*[:\-]\s*([A-Ea-e])", raw, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # Fallback: last token that is a single letter A–E
    for token in reversed(raw.split()):
        token = token.strip(".,;:")
        if re.match(r"^[A-Ea-e]$", token):
            return token.upper()
    return raw.strip()


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

        elif cls == "Solution-Title":
            if current is None:
                continue
            raw = p.get_text(strip=True)
            current.answer_label = _parse_answer_label(raw)

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

def parse_quiz_md(text: str) -> list[QuizQuestion]:
    """Parse astro-dev-id quiz markdown into QuizQuestion list.

    Expects blocks delimited by ``---`` lines, each containing:
      ``## stem``           — problem stem (one or more lines)
      ``### option``        — answer option (one per line, up to 5)
      ``<solution_title>``  — answer key line  e.g. ``<solution_title> Jawaban: D``
      remaining lines       — solution body (may contain ``$$...$$`` display math)
    """
    blocks = re.split(r"(?m)^---\s*$", text)
    questions: list[QuizQuestion] = []
    number = 0

    for block in blocks:
        q = _parse_quiz_block(block.strip())
        if q is not None:
            number += 1
            q.number = number
            questions.append(q)

    return questions


def _parse_quiz_block(block: str) -> QuizQuestion | None:
    """Parse a single question block (text between --- delimiters)."""
    if not block:
        return None

    q = QuizQuestion()
    stem_parts: list[str] = []
    solution_parts: list[str] = []
    in_solution = False

    for line in block.split("\n"):
        stripped = line.strip()

        if in_solution:
            solution_parts.append(line)
            continue

        if re.match(r"<solution_title\b", stripped, re.IGNORECASE):
            in_solution = True
            m = re.search(r"(?:Jawaban|Answer)\s*[:\-]\s*([A-Ea-e])", stripped, re.IGNORECASE)
            if m:
                q.answer_label = m.group(1).upper()
            continue

        if stripped.startswith("### "):
            q.options.append(stripped[4:].strip())
            continue

        if stripped.startswith("## "):
            stem_parts.append(stripped[3:].strip())
            continue

        # Non-empty continuation lines between ## stem and first ### are part of stem
        if stem_parts and not q.options and stripped:
            stem_parts.append(stripped)

    q.stem = " ".join(p for p in stem_parts if p).strip()
    q.solution_body = "\n".join(solution_parts).strip()

    if not q.stem and not q.options:
        return None
    return q


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

_OPTION_LETTERS = "ABCDE"


def render_astro_dev_id(result: QuizParseResult) -> str:
    """Render questions as astro-dev-id quiz markdown (## stem, ### options)."""
    blocks: list[str] = []

    for q in result.questions:
        parts: list[str] = ["---", ""]
        parts.append(f"## {q.stem}")
        parts.append("")
        for opt in q.options:
            parts.append(f"### {opt}")
            parts.append("")
        if q.answer_label:
            parts.append(f"<solution_title> Jawaban: {q.answer_label}")
            parts.append("")
        if q.solution_body:
            parts.append(q.solution_body)
            parts.append("")
        blocks.append("\n".join(parts))

    if not blocks:
        return ""
    return "\n".join(blocks) + "---\n"


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
