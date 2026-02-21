import { useState, useRef } from 'react';
import { toClipboard } from '../api';

type InputFmt = 'markdown' | 'latex';

const FORMATS: { key: InputFmt; label: string }[] = [
  { key: 'markdown', label: 'Markdown' },
  { key: 'latex', label: 'LaTeX' },
];

type Status =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ok'; formats: string[]; warnings: string[] }
  | { kind: 'error'; message: string };

export default function ToWordPanel() {
  const [fmt, setFmt] = useState<InputFmt>('markdown');
  const [text, setText] = useState('');
  const [status, setStatus] = useState<Status>({ kind: 'idle' });
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleCopy = async () => {
    if (!text.trim()) return;
    setStatus({ kind: 'loading' });
    try {
      const res = await toClipboard(text, fmt);
      setStatus({ kind: 'ok', formats: res.formats_written, warnings: res.warnings });
    } catch (err) {
      setStatus({ kind: 'error', message: err instanceof Error ? err.message : String(err) });
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Ctrl+Enter to copy
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      handleCopy();
    }
  };

  return (
    <div className="to-word-panel">
      <div className="to-word-header">
        <div className="to-word-title-tabs">
          <span className="to-word-title">Text → Word Clipboard</span>
          <div className="tabs">
            {FORMATS.map((f) => (
              <button
                key={f.key}
                className={`tab ${fmt === f.key ? 'active' : ''}`}
                onClick={() => setFmt(f.key)}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        <button
          className="copy-to-word-btn"
          onClick={handleCopy}
          disabled={!text.trim() || status.kind === 'loading'}
        >
          {status.kind === 'loading' ? (
            <>
              <span className="spinner spinner-dark" />
              Converting…
            </>
          ) : (
            'Copy to Word'
          )}
        </button>
      </div>

      <textarea
        ref={textareaRef}
        className="to-word-textarea"
        placeholder={
          fmt === 'markdown'
            ? 'Paste Markdown here (e.g. from ChatGPT / Gemini)…\n\nSupports **bold**, _italic_, # headings, tables, and $math$.'
            : 'Paste LaTeX here…\n\nSupports \\textbf{bold}, \\section{}, equations, etc.'
        }
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setStatus({ kind: 'idle' });
        }}
        onKeyDown={handleKeyDown}
        spellCheck={false}
        autoComplete="off"
      />

      <div className="to-word-footer">
        {status.kind === 'ok' && (
          <span className="to-word-status ok">
            ✓ Copied {status.formats.join(' + ')} to clipboard — paste into Word
            {status.warnings.length > 0 && (
              <span className="to-word-warnings"> ({status.warnings.join('; ')})</span>
            )}
          </span>
        )}
        {status.kind === 'error' && (
          <span className="to-word-status error">✗ {status.message}</span>
        )}
        {status.kind === 'idle' && (
          <span className="to-word-hint">Ctrl+Enter to copy</span>
        )}
      </div>
    </div>
  );
}
