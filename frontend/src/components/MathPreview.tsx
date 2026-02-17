import { useEffect, useRef } from 'react';
import katex from 'katex';
import 'katex/dist/katex.min.css';

interface Props {
  latex: string;
}

export default function MathPreview({ latex }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || !latex) return;

    const container = containerRef.current;
    container.innerHTML = '';

    // Split by display and inline math delimiters and render each part
    const parts = splitMath(latex);

    for (const part of parts) {
      if (part.type === 'display') {
        const div = document.createElement('div');
        div.className = 'math-preview-block';
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
        span.className = 'math-preview-inline';
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
  }, [latex]);

  if (!latex) {
    return <div className="math-preview empty">No output to preview</div>;
  }

  return (
    <div className="math-preview" ref={containerRef} />
  );
}

interface MathPart {
  type: 'text' | 'inline' | 'display';
  content: string;
}

function splitMath(latex: string): MathPart[] {
  const parts: MathPart[] = [];
  // Match \[...\] or $$...$$ for display, $...$ for inline
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
