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

    if (mode === 'latex') {
      renderLatex(container, content);
    } else if (mode === 'markdown') {
      renderMarkdown(container, content);
    } else {
      renderHtml(container, content);
    }
  }, [content, mode]);

  if (!content) {
    return <div className="preview empty">No output to preview</div>;
  }

  return (
    <div
      className={`preview preview-${mode}`}
      ref={containerRef}
    />
  );
}

/* ── LaTeX mode ── */

function renderLatex(container: HTMLDivElement, latex: string) {
  container.innerHTML = '';
  const parts = splitMath(latex);

  for (const part of parts) {
    if (part.type === 'display') {
      const div = document.createElement('div');
      div.className = 'math-block';
      try {
        katex.render(part.content, div, {
          displayMode: true,
          throwOnError: false,
          output: 'html',
        });
      } catch {
        div.textContent = part.content;
      }
      container.appendChild(div);
    } else if (part.type === 'inline') {
      const span = document.createElement('span');
      span.className = 'math-inline';
      try {
        katex.render(part.content, span, {
          displayMode: false,
          throwOnError: false,
          output: 'html',
        });
      } catch {
        span.textContent = part.content;
      }
      container.appendChild(span);
    } else {
      const span = document.createElement('span');
      span.textContent = part.content;
      container.appendChild(span);
    }
  }
}

/* ── Markdown mode ── */

function renderMarkdown(container: HTMLDivElement, md: string) {
  // Step 1: Extract math blocks and replace with HTML placeholders
  // We use <span data-math-id="N"> tags so marked passes them through untouched
  // (unlike __MATH_N__ which marked converts to <strong>MATH_N</strong>)
  const mathStore: { idx: number; tex: string; display: boolean }[] = [];
  let nextIdx = 0;

  let processed = md.replace(/\$\$([\s\S]*?)\$\$/g, (_match, inner) => {
    const i = nextIdx++;
    mathStore.push({ idx: i, tex: inner.trim(), display: true });
    return `<span data-math-id="${i}"></span>`;
  });
  processed = processed.replace(/\$([^$\n]+?)\$/g, (_match, inner) => {
    const i = nextIdx++;
    mathStore.push({ idx: i, tex: inner, display: false });
    return `<span data-math-id="${i}"></span>`;
  });

  // Step 2: Render markdown to HTML
  const html = marked.parse(processed, { async: false }) as string;

  // Step 3: Insert rendered HTML
  container.innerHTML = html;

  // Step 4: Find placeholder spans and replace with KaTeX-rendered math
  for (const { idx, tex, display } of mathStore) {
    const placeholder = container.querySelector(`[data-math-id="${idx}"]`);
    if (!placeholder) continue;

    const el = display
      ? document.createElement('div')
      : document.createElement('span');
    el.className = display ? 'math-block' : 'math-inline';

    try {
      katex.render(tex, el, {
        displayMode: display,
        throwOnError: false,
        output: 'html',
      });
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

/* ── Math splitter (shared with LaTeX mode) ── */

interface MathPart {
  type: 'text' | 'inline' | 'display';
  content: string;
}

function splitMath(latex: string): MathPart[] {
  const parts: MathPart[] = [];
  const regex = /(\\\[[\s\S]*?\\\]|\$\$[\s\S]*?\$\$|\$[^$]+?\$)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(latex)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: 'text', content: latex.slice(lastIndex, match.index) });
    }

    const matched = match[0];
    if (matched.startsWith('\\[')) {
      parts.push({ type: 'display', content: matched.slice(2, -2).trim() });
    } else if (matched.startsWith('$$')) {
      parts.push({ type: 'display', content: matched.slice(2, -2).trim() });
    } else {
      parts.push({ type: 'inline', content: matched.slice(1, -1) });
    }

    lastIndex = match.index + matched.length;
  }

  if (lastIndex < latex.length) {
    parts.push({ type: 'text', content: latex.slice(lastIndex) });
  }

  return parts;
}
