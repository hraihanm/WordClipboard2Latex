"""Post-process LaTeX output to clean up Pandoc quirks."""

from __future__ import annotations

import re


def postprocess_latex(latex: str) -> str:
    """Clean up LaTeX math output from Pandoc."""
    latex = _unwrap_multiline_groups(latex)
    latex = _unwrap_array_in_aligned(latex)
    latex = _collapse_nested_aligned(latex)
    latex = _add_alignment_markers(latex)
    latex = _fix_bold_math_vars(latex)
    latex = _fix_log_subscript(latex)
    latex = _fix_whitespace(latex)
    latex = _fix_common_pandoc_quirks(latex)
    latex = _fix_number_unit_spacing(latex)
    return latex.strip()


def _unwrap_multiline_groups(latex: str) -> str:
    r"""Convert Pandoc's multi-oMath output into aligned rows.

    When <m:oMathPara> contains multiple <m:oMath>, Pandoc produces either:
      {line1\n}{line2\n}{line3\n}{line4}   (with newlines)
    or:
      {line1}{line2}{line3}{line4}          (without newlines)

    Convert to:
      line1 \\
      line2 \\
      line3 \\
      line4

    Key distinction from \frac{a}{b}:
    - Multiline groups: the ENTIRE string consists only of consecutive
      top-level groups, each containing substantial equation content.
    - Command arguments: groups appear after a command like \frac and
      are typically short (single chars/expressions).
    """
    # Split into top-level brace groups.  Walk the string tracking brace
    # depth so we don't confuse \frac{a}{b} with multiline groups.
    groups: list[str] = []
    depth = 0
    start = -1

    for i, ch in enumerate(latex):
        if ch == '{' and depth == 0:
            start = i
            depth = 1
        elif ch == '{':
            depth += 1
        elif ch == '}' and depth > 0:
            depth -= 1
            if depth == 0 and start >= 0:
                groups.append((start, i, latex[start + 1:i]))
                start = -1

    if len(groups) < 2:
        return latex

    # Verify no non-whitespace content between consecutive groups
    is_consecutive = True
    for j in range(len(groups) - 1):
        between = latex[groups[j][1] + 1:groups[j + 1][0]]
        if between.strip():
            is_consecutive = False
            break

    if not is_consecutive:
        return latex

    # Check that content before first group and after last is just whitespace
    before = latex[:groups[0][0]].strip()
    after = latex[groups[-1][1] + 1:].strip()
    if before or after:
        return latex

    # Heuristic to distinguish multiline equations from \frac{a}{b}-style args:
    # - If any groups contain newlines → multiline (original Pandoc behavior)
    # - If 3+ groups → multiline (e.g. 4-line equation system)
    # - If 2 groups, each with substantial content (>5 chars) → multiline
    newline_groups = sum(1 for _, _, c in groups if '\n' in c)
    if newline_groups >= 1:
        pass  # definitely multiline
    elif len(groups) >= 3:
        pass  # 3+ consecutive groups = multiline
    elif len(groups) == 2:
        # 2 groups: only multiline if both have substantial content
        # (rules out \frac{a}{b} or _{10} style)
        contents = [c.strip() for _, _, c in groups]
        if all(len(c) > 5 for c in contents):
            pass  # substantial content in both
        else:
            return latex  # likely command arguments
    else:
        return latex

    # Extract and join the lines
    lines = [content.strip() for _, _, content in groups]
    return ' \\\\\n'.join(lines)


def _unwrap_array_in_aligned(latex: str) -> str:
    r"""Replace \begin{array}{r}...\end{array} inside aligned with just the rows.

    Pandoc produces:
      \begin{array}{r}
      line1 \\
      line2
      \end{array}

    We want just:
      line1 \\
      line2
    """
    latex = re.sub(
        r'\\begin\{array\}\{[^}]*\}\s*(.*?)\s*\\end\{array\}',
        r'\1',
        latex,
        flags=re.DOTALL,
    )
    return latex


def _collapse_nested_aligned(latex: str) -> str:
    r"""Collapse nested aligned environments.

    Pandoc sometimes produces:
      \begin{aligned} \begin{aligned} ... \end{aligned} \end{aligned}
    """
    pattern = r'\\begin\{aligned\}\s*\\begin\{aligned\}'
    while re.search(pattern, latex):
        latex = re.sub(pattern, r'\\begin{aligned}', latex)
        latex = re.sub(
            r'\\end\{aligned\}\s*\\end\{aligned\}',
            r'\\end{aligned}',
            latex,
        )
    return latex


# Relation operators for alignment, ordered by specificity.
# LaTeX commands use negative lookahead to avoid matching prefixes
# (e.g. \le inside \left).
_RELATION_OPS = [
    r'\\approx(?![a-zA-Z])', r'\\simeq(?![a-zA-Z])', r'\\cong(?![a-zA-Z])',
    r'\\equiv(?![a-zA-Z])', r'\\sim(?![a-zA-Z])',
    r'\\propto(?![a-zA-Z])', r'\\doteq(?![a-zA-Z])',
    r'\\leq(?![a-zA-Z])', r'\\le(?![a-zA-Z])',
    r'\\geq(?![a-zA-Z])', r'\\ge(?![a-zA-Z])',
    r'\\ll(?![a-zA-Z])', r'\\gg(?![a-zA-Z])',
    r'\\neq(?![a-zA-Z])', r'\\ne(?![a-zA-Z])',
    r'\\to(?![a-zA-Z])', r'\\rightarrow(?![a-zA-Z])', r'\\leftarrow(?![a-zA-Z])',
    r'\\Rightarrow(?![a-zA-Z])', r'\\Leftarrow(?![a-zA-Z])',
    r'\\Leftrightarrow(?![a-zA-Z])', r'\\iff(?![a-zA-Z])',
    r'=',
    r'(?<!\\)<(?![a-zA-Z])',
    r'(?<!\\)>(?![a-zA-Z])',
]


def _add_alignment_markers(latex: str) -> str:
    r"""Add & before the first relation operator on each line of multiline math.

    For lines separated by \\, find the leftmost relation operator (=,
    \Rightarrow, etc.) that is NOT inside braces, and insert & before it.

    Input:  m - M = -5 + 5\log_{10}d \\  M = m + 5
    Output: m - M &= -5 + 5\log_{10}d \\  M &= m + 5
    """
    # Only process multiline content (has \\)
    if '\\\\' not in latex:
        return latex

    lines = re.split(r'\s*\\\\\s*', latex)
    if len(lines) < 2:
        return latex

    aligned_lines = []
    for line in lines:
        aligned_lines.append(_insert_alignment(line))

    return ' \\\\\n'.join(aligned_lines)


def _insert_alignment(line: str) -> str:
    """Insert & before the leftmost relation operator NOT inside braces."""
    # Already has alignment marker
    if '&' in line:
        return line

    best_pos = len(line) + 1
    best_match = None

    for op_pattern in _RELATION_OPS:
        for m in re.finditer(op_pattern, line):
            pos = m.start()

            # Check brace depth at this position — skip if inside braces
            depth = 0
            for ch in line[:pos]:
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
            if depth > 0:
                continue

            if pos < best_pos:
                best_pos = pos
                best_match = m
            break  # first match per operator is enough

    if best_match is not None:
        pos = best_match.start()
        return line[:pos] + '&' + line[pos:]

    return line


def _fix_bold_math_vars(latex: str) -> str:
    r"""Convert \mathbf{x} to just x for single-letter variables.

    Word marks equation variables as bold-italic via <m:sty m:val="bi"/>,
    which Pandoc translates to \mathbf{}. In standard math notation these
    should just be plain (italic) variables.
    """
    # \mathbf{x} where x is a single letter → just x
    latex = re.sub(r'\\mathbf\{(\w)\}', r'\1', latex)
    # \mathbf{text} for short identifiers — also unwrap
    latex = re.sub(r'\\mathbf\{(\w+)\}', r'\1', latex)
    return latex


def _fix_log_subscript(latex: str) -> str:
    r"""Fix Pandoc's \log\ _{10} → \log_{10}.

    Pandoc inserts an extra \ (backslash-space) before the subscript of
    function names like log.
    """
    # \log\ _{10} → \log_{10}
    latex = re.sub(r'(\\log)\\\s*_\{', r'\1_{', latex)
    # Also handle: \log\ _{10} without braces (less common)
    latex = re.sub(r'(\\log)\\\s*_(\w)', r'\1_{\2}', latex)
    return latex


def _fix_whitespace(latex: str) -> str:
    """Normalize whitespace in LaTeX output."""
    # Collapse multiple spaces
    latex = re.sub(r'  +', ' ', latex)
    # Ensure line breaks in aligned environments are clean
    latex = re.sub(r'\s*\\\\\s*', ' \\\\\\\\\n', latex)
    # Remove trailing whitespace on lines
    latex = '\n'.join(line.rstrip() for line in latex.splitlines())
    return latex


def _fix_number_unit_spacing(latex: str) -> str:
    r"""Insert a thin space (\,) between a number and a \text{…} unit label.

    In LaTeX math mode, plain spaces are ignored, so ``5407 \text{Å}`` and
    ``5407\text{Å}`` render identically — with no visible gap.  The correct
    typographic convention (ISO 80000 / siunitx) is a thin space:

        5407\,\text{Å}

    This rule fires when a digit is followed by optional whitespace and then
    ``\text{``.  It does *not* touch letter-to-\text patterns (e.g. ``x\text{th}``)
    because those are usually ordinal suffixes that need no space.
    """
    return re.sub(r'(\d)\s*(\\text\{)', r'\1\\,\2', latex)


def _fix_common_pandoc_quirks(latex: str) -> str:
    """Fix known Pandoc conversion artifacts."""
    # \text{ } (just a space) should be removed
    latex = re.sub(r'\\text\{\s*\}', ' ', latex)

    # Fix double backslash spacing
    latex = re.sub(r'\\\\\\\\', r'\\\\', latex)

    # Remove empty groups
    latex = re.sub(r'\{\}', '', latex)

    # Fix \left and \right spacing
    latex = re.sub(r'\\left\s+', r'\\left', latex)
    latex = re.sub(r'\\right\s+', r'\\right', latex)

    return latex
