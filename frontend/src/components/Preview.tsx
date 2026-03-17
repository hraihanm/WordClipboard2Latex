import { useEffect, useRef } from 'react';
import katex from 'katex';
import { marked } from 'marked';
import 'katex/dist/katex.min.css';

type PreviewMode = 'markdown' | 'latex' | 'html';

interface Props {
  content: string;
  mode: PreviewMode;
}

export default function Preview({ content, mode }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || !content) return;
    const container = containerRef.current;
    if (mode === 'latex') renderLatex(container, content);
    else if (mode === 'markdown') renderMarkdown(container, content);
    else renderHtml(container, content);
  }, [content, mode]);

  if (!content) {
    return <div className="preview empty">No output to preview</div>;
  }

  return <div className={`preview preview-${mode}`} ref={containerRef} />;
}

/* ── LaTeX mode ── */

/**
 * Convert a LaTeX text fragment (no math) to HTML.
 * Handles sections, formatting, lists, verbatim, special characters, and paragraphs.
 * Math has already been extracted and replaced with %%DMATH_N%% / %%IMATH_N%% tokens.
 */
function latexToHtml(text: string): string {
  // Remove document wrapper — keep only body content
  const bodyMatch = text.match(/\\begin\{document\}([\s\S]*?)(?:\\end\{document\}|$)/);
  if (bodyMatch) text = bodyMatch[1];

  // Strip preamble commands
  text = text.replace(
    /\\(?:documentclass|usepackage|geometry|hypersetup|setlength|setcounter|pagestyle|thispagestyle|renewcommand|newcommand|providecommand)(?:\[[^\]]*\])?(?:\{[^}]*\})*/g,
    '',
  );
  text = text.replace(/\\(?:title|author|date|maketitle|tableofcontents)\b(?:\s*\{[^}]*\})?/g, '');

  // Verbatim environments (must come before general command stripping)
  text = text.replace(
    /\\begin\{verbatim\}([\s\S]*?)\\end\{verbatim\}/g,
    '<pre><code>$1</code></pre>',
  );
  text = text.replace(/\\verb\|([^|]*)\|/g, '<code>$1</code>');
  text = text.replace(/\\verb\+([^+]*)\+/g, '<code>$1</code>');

  // Sections → headings
  text = text.replace(/\\chapter\*?\{([^{}]*)\}/g,        '\n<h1>$1</h1>\n');
  text = text.replace(/\\section\*?\{([^{}]*)\}/g,        '\n<h2>$1</h2>\n');
  text = text.replace(/\\subsection\*?\{([^{}]*)\}/g,     '\n<h3>$1</h3>\n');
  text = text.replace(/\\subsubsection\*?\{([^{}]*)\}/g,  '\n<h4>$1</h4>\n');
  text = text.replace(/\\paragraph\*?\{([^{}]*)\}/g,      '\n<h5>$1</h5>\n');

  // Text formatting
  text = text.replace(/\\textbf\{([^{}]*)\}/g,            '<strong>$1</strong>');
  text = text.replace(/\\textit\{([^{}]*)\}/g,            '<em>$1</em>');
  text = text.replace(/\\emph\{([^{}]*)\}/g,              '<em>$1</em>');
  text = text.replace(/\\texttt\{([^{}]*)\}/g,            '<code>$1</code>');
  text = text.replace(/\\underline\{([^{}]*)\}/g,         '<u>$1</u>');
  text = text.replace(/\\textsc\{([^{}]*)\}/g,            '<span style="font-variant:small-caps">$1</span>');
  text = text.replace(/\\textsuperscript\{([^{}]*)\}/g,   '<sup>$1</sup>');
  text = text.replace(/\\textsubscript\{([^{}]*)\}/g,     '<sub>$1</sub>');

  // Lists (process innermost first via repeated replacement)
  for (let pass = 0; pass < 3; pass++) {
    text = text.replace(/\\begin\{itemize\}([\s\S]*?)\\end\{itemize\}/g, (_, inner) => {
      const items = inner
        .split(/\\item\b/)
        .filter((s: string) => s.trim())
        .map((s: string) => s.replace(/^\[[^\]]*\]/, '').trim());
      return `<ul>${items.map((s: string) => `<li>${s}</li>`).join('')}</ul>`;
    });
    text = text.replace(/\\begin\{enumerate\}([\s\S]*?)\\end\{enumerate\}/g, (_, inner) => {
      const items = inner
        .split(/\\item\b/)
        .filter((s: string) => s.trim())
        .map((s: string) => s.replace(/^\[[^\]]*\]/, '').trim());
      return `<ol>${items.map((s: string) => `<li>${s}</li>`).join('')}</ol>`;
    });
    text = text.replace(/\\begin\{description\}([\s\S]*?)\\end\{description\}/g, (_, inner) => {
      const items = inner.split(/\\item\b/).filter((s: string) => s.trim());
      return `<dl>${items.map((s: string) => {
        const m = s.match(/^\[([^\]]*)\]([\s\S]*)/);
        return m
          ? `<dt><strong>${m[1]}</strong></dt><dd>${m[2].trim()}</dd>`
          : `<dd>${s.trim()}</dd>`;
      }).join('')}</dl>`;
    });
  }

  // Block environments
  text = text.replace(
    /\\begin\{(?:quote|quotation)\}([\s\S]*?)\\end\{(?:quote|quotation)\}/g,
    '<blockquote>$1</blockquote>',
  );
  text = text.replace(
    /\\begin\{abstract\}([\s\S]*?)\\end\{abstract\}/g,
    '<blockquote><em>Abstract:</em> $1</blockquote>',
  );
  text = text.replace(
    /\\begin\{center\}([\s\S]*?)\\end\{center\}/g,
    '<div style="text-align:center">$1</div>',
  );

  // Strip remaining environments
  text = text.replace(/\\(?:begin|end)\{[^}]*\}/g, '');

  // Line breaks
  text = text.replace(/\\\\\s*(?:\[[^\]]*\])?/g, '<br>');
  text = text.replace(/\\newline\b/g, '<br>');
  text = text.replace(/\\(?:medskip|bigskip|smallskip)\b/g, '<br>');

  // Special characters
  text = text.replace(/\\&/g,  '&amp;');
  text = text.replace(/\\%/g,  '%');
  text = text.replace(/\\#/g,  '#');
  text = text.replace(/\\_/g,  '_');
  text = text.replace(/\\textbackslash\b(?:\{\})?/g, '\\');
  text = text.replace(/\\ldots\b|\\dots\b/g, '…');
  text = text.replace(/---/g, '—');
  text = text.replace(/--/g,  '–');
  text = text.replace(/``/g,  '\u201C');
  text = text.replace(/''/g,  '\u201D');

  // Spacing commands
  text = text.replace(/\\[hv]space\*?\{[^}]*\}/g, '');
  text = text.replace(/\\(?:quad|qquad|enspace|thinspace|medspace|thickspace)\b/g, '\u2003');
  text = text.replace(/\\[,;:>!]/g, '\u2009');

  // References / citations
  text = text.replace(/\\label\{[^}]*\}/g, '');
  text = text.replace(/\\(?:ref|eqref|pageref)\{([^}]*)\}/g, '[$1]');
  text = text.replace(/\\cite(?:\[[^\]]*\])?\{[^}]*\}/g, '');
  text = text.replace(/\\footnote\{([^{}]*)\}/g, '<sup title="$1">†</sup>');

  // Remaining commands with one brace argument — keep the inner content
  text = text.replace(/\\[a-zA-Z]+\*?(?:\[[^\]]*\])*\{([^{}]*)\}/g, '$1');

  // Strip bare commands and leftover braces
  text = text.replace(/\\[a-zA-Z@]+\*?/g, '');
  text = text.replace(/\\[^a-zA-Z\s]/g, '');
  text = text.replace(/[{}]/g, '');

  // Paragraph splitting (double newline → <p>)
  const BLOCK_RE = /^<(?:h[1-6]|ul|ol|dl|pre|div|blockquote|hr|table)[\s>]/i;
  const blocks = text.split(/\n{2,}/);
  return blocks
    .map(block => {
      block = block.trim();
      if (!block) return '';
      if (BLOCK_RE.test(block)) return block;
      block = block.replace(/\n/g, ' ').replace(/\s+/g, ' ').trim();
      if (!block) return '';
      return `<p>${block}</p>`;
    })
    .filter(Boolean)
    .join('\n');
}

function renderLatex(container: HTMLDivElement, latex: string) {
  // Strip comments before any processing (% is the LaTeX comment character)
  let text = latex.replace(/%[^\n]*/g, '');

  const mathStore: { idx: number; tex: string; display: boolean }[] = [];
  let nextIdx = 0;

  // Named display math environments
  text = text.replace(
    /\\begin\{(equation|align|gather|multline|eqnarray)\*?\}([\s\S]*?)\\end\{\1\*?\}/g,
    (_, _env, inner) => {
      const i = nextIdx++;
      mathStore.push({ idx: i, tex: inner.trim(), display: true });
      return `\n\n%%DMATH${i}%%\n\n`;
    },
  );

  // \[...\] display math
  text = text.replace(/\\\[([\s\S]*?)\\\]/g, (_, inner) => {
    const i = nextIdx++;
    mathStore.push({ idx: i, tex: inner.trim(), display: true });
    return `\n\n%%DMATH${i}%%\n\n`;
  });

  // $$...$$ display math
  text = text.replace(/\$\$([\s\S]*?)\$\$/g, (_, inner) => {
    const i = nextIdx++;
    mathStore.push({ idx: i, tex: inner.trim(), display: true });
    return `\n\n%%DMATH${i}%%\n\n`;
  });

  // $...$ inline math
  text = text.replace(/\$([^$\n]+?)\$/g, (_, inner) => {
    const i = nextIdx++;
    mathStore.push({ idx: i, tex: inner, display: false });
    return `%%IMATH${i}%%`;
  });

  // Convert remaining LaTeX text to HTML
  let html = latexToHtml(text);

  // Restore display math: <p>%%DMATHn%%</p>  →  <div data-math-id="n">
  html = html.replace(/<p>\s*%%DMATH(\d+)%%\s*<\/p>/g, '<div data-math-id="$1"></div>');
  html = html.replace(/%%DMATH(\d+)%%/g, '<div data-math-id="$1"></div>');

  // Restore inline math
  html = html.replace(/%%IMATH(\d+)%%/g, '<span data-math-id="$1"></span>');

  container.innerHTML = html;

  // Render math placeholders with KaTeX
  for (const { idx, tex, display } of mathStore) {
    const placeholder = container.querySelector(`[data-math-id="${idx}"]`) as HTMLElement | null;
    if (!placeholder) continue;

    const el = document.createElement(display ? 'div' : 'span');
    el.className = display ? 'math-block' : 'math-inline';
    try {
      katex.render(tex, el, { displayMode: display, throwOnError: false, output: 'html' });
    } catch {
      el.textContent = display ? `\\[${tex}\\]` : `$${tex}$`;
    }
    placeholder.replaceWith(el);
  }
}

/* ── Markdown mode ── */

function renderMarkdown(container: HTMLDivElement, md: string) {
  const mathStore: { idx: number; tex: string; display: boolean }[] = [];
  let nextIdx = 0;

  // Extract $$...$$ display math
  let processed = md.replace(/\$\$([\s\S]*?)\$\$/g, (_match, inner) => {
    const i = nextIdx++;
    mathStore.push({ idx: i, tex: inner.trim(), display: true });
    return `<span data-math-id="${i}"></span>`;
  });

  // Extract $...$ inline math
  processed = processed.replace(/\$([^$\n]+?)\$/g, (_match, inner) => {
    const i = nextIdx++;
    mathStore.push({ idx: i, tex: inner, display: false });
    return `<span data-math-id="${i}"></span>`;
  });

  container.innerHTML = marked.parse(processed, { async: false }) as string;

  for (const { idx, tex, display } of mathStore) {
    const placeholder = container.querySelector(`[data-math-id="${idx}"]`);
    if (!placeholder) continue;

    const el = display ? document.createElement('div') : document.createElement('span');
    el.className = display ? 'math-block' : 'math-inline';
    try {
      katex.render(tex, el, { displayMode: display, throwOnError: false, output: 'html' });
    } catch {
      el.textContent = tex;
    }
    placeholder.replaceWith(el);
  }
}

/* ── HTML mode ── */

function renderHtml(container: HTMLDivElement, html: string) {
  container.innerHTML = html;
}
