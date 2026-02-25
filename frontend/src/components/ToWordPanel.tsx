import { useState, useRef } from 'react';
import { toClipboard, exportDocx } from '../api';
import Preview from './Preview';

type InputFmt = 'markdown' | 'latex';

const FORMATS: { key: InputFmt; label: string }[] = [
  { key: 'markdown', label: 'Markdown' },
  { key: 'latex',    label: 'LaTeX' },
];

type Status =
  | { kind: 'idle' }
  | { kind: 'loading'; action: 'clipboard' | 'docx' }
  | { kind: 'ok'; message: string }
  | { kind: 'error'; message: string };

export default function ToWordPanel() {
  const [fmt, setFmt]       = useState<InputFmt>('markdown');
  const [text, setText]     = useState('');
  const [status, setStatus] = useState<Status>({ kind: 'idle' });
  const textareaRef         = useRef<HTMLTextAreaElement>(null);

  const handleCopy = async () => {
    if (!text.trim()) return;
    setStatus({ kind: 'loading', action: 'clipboard' });
    try {
      const res = await toClipboard(text, fmt);
      const msg = `Copied ${res.formats_written.join(' + ')} to clipboard — paste into Word`;
      setStatus({ kind: 'ok', message: msg });
    } catch (err) {
      setStatus({ kind: 'error', message: err instanceof Error ? err.message : String(err) });
    }
  };

  const handleExportDocx = async () => {
    if (!text.trim()) return;
    setStatus({ kind: 'loading', action: 'docx' });
    try {
      await exportDocx(text, fmt);
      setStatus({ kind: 'ok', message: 'output.docx downloaded' });
    } catch (err) {
      setStatus({ kind: 'error', message: err instanceof Error ? err.message : String(err) });
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      handleCopy();
    }
  };

  const isBusy = status.kind === 'loading';

  return (
    <div className="to-word-panel">

      {/* Header */}
      <div className="to-word-header">
        <div className="to-word-title-tabs">
          <span className="to-word-title">Input</span>
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
        <div className="to-word-actions">
          <button
            className="copy-to-word-btn"
            onClick={handleCopy}
            disabled={!text.trim() || isBusy}
          >
            {status.kind === 'loading' && status.action === 'clipboard'
              ? <><span className="spinner spinner-dark" />Converting…</>
              : 'Copy to Word'}
          </button>
          <button
            className="export-docx-btn"
            onClick={handleExportDocx}
            disabled={!text.trim() || isBusy}
          >
            {status.kind === 'loading' && status.action === 'docx'
              ? <><span className="spinner spinner-dark" />Exporting…</>
              : 'Export .docx'}
          </button>
        </div>
      </div>

      {/* Body: textarea left, preview right */}
      <div className="to-word-body">
        <textarea
          ref={textareaRef}
          className="to-word-textarea"
          placeholder={
            fmt === 'markdown'
              ? 'Paste Markdown here…\n\nSupports **bold**, _italic_, # headings, tables, and $math$.'
              : 'Paste LaTeX here…\n\nSupports \\textbf{bold}, \\section{}, equations, etc.'
          }
          value={text}
          onChange={(e) => { setText(e.target.value); setStatus({ kind: 'idle' }); }}
          onKeyDown={handleKeyDown}
          spellCheck={false}
          autoComplete="off"
        />
        <div className="to-word-preview">
          <div className="to-word-preview-label">Preview</div>
          <div className="to-word-preview-content">
            {text.trim()
              ? <Preview content={text} mode={fmt} />
              : <span className="to-word-preview-empty">Preview will appear as you type</span>
            }
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="to-word-footer">
        {status.kind === 'ok' && <span className="to-word-status ok">✓ {status.message}</span>}
        {status.kind === 'error' && <span className="to-word-status error">✗ {status.message}</span>}
        {status.kind === 'idle' && <span className="to-word-hint">Ctrl+Enter to copy to Word</span>}
      </div>

    </div>
  );
}
