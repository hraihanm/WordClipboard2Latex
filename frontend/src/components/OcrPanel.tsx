import { useCallback, useEffect, useRef, useState } from 'react';
import { ocrImage, toClipboard, exportDocx, translateText } from '../api';
import CodeOutput from './CodeOutput';
import CopyButton from './CopyButton';
import Preview from './Preview';
import Select from './Select';

type Backend    = 'gemini' | 'got';
type Format     = 'markdown' | 'latex';
type LangOption = 'none' | 'English' | 'Indonesian';

type ActionStatus =
  | { kind: 'idle' }
  | { kind: 'loading'; action: 'ocr' | 'translate' | 'clipboard' | 'docx' }
  | { kind: 'ok';    message: string }
  | { kind: 'error'; message: string };

const BACKEND_OPTIONS = [
  { value: 'gemini', label: 'Gemini Flash' },
  { value: 'got',    label: 'GOT-OCR (local)' },
];

const FORMAT_OPTIONS = [
  { value: 'markdown', label: 'Markdown' },
  { value: 'latex',    label: 'LaTeX' },
];

const LANG_OPTIONS = [
  { value: 'none',       label: 'No translation' },
  { value: 'English',    label: 'English' },
  { value: 'Indonesian', label: 'Indonesian' },
];

export default function OcrPanel() {
  const [image, setImage]       = useState<File | Blob | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [backend, setBackend]   = useState<Backend>('gemini');
  const [format, setFormat]     = useState<Format>('markdown');
  const [targetLang, setTargetLang] = useState<LangOption>('none');

  const [ocrResult, setOcrResult]         = useState<string | null>(null);
  const [displayResult, setDisplayResult] = useState<string | null>(null);
  const [isTranslated, setIsTranslated]   = useState(false);

  const [status, setStatus] = useState<ActionStatus>({ kind: 'idle' });
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isBusy = status.kind === 'loading';

  // ── Image loading ─────────────────────────────────────
  const loadImage = useCallback((blob: File | Blob) => {
    setImage(blob);
    setOcrResult(null);
    setDisplayResult(null);
    setIsTranslated(false);
    setStatus({ kind: 'idle' });
    setImageUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(blob);
    });
  }, []);

  useEffect(() => {
    const handler = (e: ClipboardEvent) => {
      if (!e.clipboardData) return;
      const item = Array.from(e.clipboardData.items).find((i) => i.type.startsWith('image/'));
      if (item) { const b = item.getAsFile(); if (b) loadImage(b); }
    };
    window.addEventListener('paste', handler);
    return () => window.removeEventListener('paste', handler);
  }, [loadImage]);

  const onDragOver  = (e: React.DragEvent) => { e.preventDefault(); setDragging(true); };
  const onDragLeave = () => setDragging(false);
  const onDrop      = (e: React.DragEvent) => {
    e.preventDefault(); setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f?.type.startsWith('image/')) loadImage(f);
  };
  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (f) loadImage(f); e.target.value = '';
  };
  const clearImage = (e: React.MouseEvent) => {
    e.stopPropagation();
    setImage(null);
    setImageUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return null; });
    setOcrResult(null); setDisplayResult(null); setIsTranslated(false);
    setStatus({ kind: 'idle' });
  };

  // ── Actions ────────────────────────────────────────────
  const handleOcr = async () => {
    if (!image) return;
    setStatus({ kind: 'loading', action: 'ocr' });
    setOcrResult(null); setDisplayResult(null); setIsTranslated(false);
    try {
      const res = await ocrImage(image, backend, format);
      setOcrResult(res.result);
      setDisplayResult(res.result);
      setStatus({ kind: 'idle' });
    } catch (err) {
      setStatus({ kind: 'error', message: err instanceof Error ? err.message : 'OCR failed' });
    }
  };

  const handleTranslate = async () => {
    if (!ocrResult || targetLang === 'none') return;
    setStatus({ kind: 'loading', action: 'translate' });
    try {
      const result = await translateText(ocrResult, targetLang, format);
      setDisplayResult(result); setIsTranslated(true);
      setStatus({ kind: 'idle' });
    } catch (err) {
      setStatus({ kind: 'error', message: err instanceof Error ? err.message : 'Translation failed' });
    }
  };

  const handleCopyToWord = async () => {
    if (!displayResult) return;
    setStatus({ kind: 'loading', action: 'clipboard' });
    try {
      await toClipboard(displayResult, format);
      setStatus({ kind: 'ok', message: 'Copied to clipboard — paste into Word' });
    } catch (err) {
      setStatus({ kind: 'error', message: err instanceof Error ? err.message : 'Failed' });
    }
  };

  const handleExportDocx = async () => {
    if (!displayResult) return;
    setStatus({ kind: 'loading', action: 'docx' });
    try {
      await exportDocx(displayResult, format);
      setStatus({ kind: 'ok', message: 'output.docx downloaded' });
    } catch (err) {
      setStatus({ kind: 'error', message: err instanceof Error ? err.message : 'Failed' });
    }
  };

  // ── Render ─────────────────────────────────────────────
  return (
    <div className="ocr-panel">

      {/* ── Row 0: Controls ── */}
      <div className="ocr-controls">
        <div className="ocr-selects">
          <label className="ocr-label">Backend</label>
          <Select value={backend} options={BACKEND_OPTIONS} onChange={(v) => setBackend(v as Backend)} disabled={isBusy} />
          <label className="ocr-label">Output</label>
          <Select
            value={format} options={FORMAT_OPTIONS}
            onChange={(v) => { setFormat(v as Format); setOcrResult(null); setDisplayResult(null); setIsTranslated(false); }}
            disabled={isBusy}
          />
          <label className="ocr-label">Translate to</label>
          <Select
            value={targetLang} options={LANG_OPTIONS}
            onChange={(v) => { setTargetLang(v as LangOption); setStatus({ kind: 'idle' }); }}
            disabled={isBusy}
          />
        </div>
        <button className="convert-btn" onClick={handleOcr} disabled={!image || isBusy}>
          {status.kind === 'loading' && status.action === 'ocr' && <span className="spinner" />}
          {status.kind === 'loading' && status.action === 'ocr' ? 'Running OCR…' : 'Run OCR'}
        </button>
      </div>

      {/* ── Row 1: Image | Preview ── */}
      <div className="ocr-row-top">

        {/* Image zone */}
        <div
          className={`ocr-dropzone${dragging ? ' dragging' : ''}${imageUrl ? ' has-image' : ''}`}
          onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}
          onClick={() => !imageUrl && fileInputRef.current?.click()}
        >
          {imageUrl ? (
            <>
              <img src={imageUrl} alt="Input" className="ocr-preview-img" />
              <button className="ocr-clear-btn" onClick={clearImage} title="Remove">✕</button>
            </>
          ) : (
            <div className="ocr-dropzone-hint">
              <span className="ocr-dropzone-icon">⬆</span>
              <span>Drop image here or <span className="ocr-link" onClick={() => fileInputRef.current?.click()}>browse</span></span>
              <span className="ocr-dropzone-sub">Ctrl+V to paste from clipboard</span>
            </div>
          )}
          <input ref={fileInputRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={onFileChange} />
        </div>

        {/* Rendered preview */}
        <div className="ocr-preview-zone">
          <div className="ocr-zone-header">
            <span className="panel-label">Preview</span>
            {isTranslated && (
              <span className="ocr-translated-badge">
                {targetLang}
                <button className="ocr-reset-link" onClick={() => { setDisplayResult(ocrResult); setIsTranslated(false); }}>
                  original
                </button>
              </span>
            )}
          </div>
          <div className="ocr-preview-scroll">
            {displayResult
              ? <Preview content={displayResult} mode={format} />
              : <span className="ocr-zone-empty">
                  {status.kind === 'loading' && status.action === 'ocr' ? 'Processing…' : 'Preview will appear here'}
                </span>
            }
          </div>
        </div>

      </div>

      {/* ── Row 2: Code output ── */}
      <div className="ocr-row-code">
        <div className="ocr-zone-header">
          <span className="panel-label">Code</span>
          <CopyButton text={displayResult ?? ''} />
        </div>
        <div className="ocr-code-scroll">
          {displayResult
            ? <CodeOutput content={displayResult} language={format} />
            : <span className="ocr-zone-empty">
                {status.kind === 'loading' && status.action === 'ocr' ? 'Processing…' : 'Generated code will appear here'}
              </span>
          }
        </div>
      </div>

      {/* ── Footer ── */}
      <div className="ocr-footer">
        <div className="ocr-footer-actions">
          <button className="translate-btn" onClick={handleTranslate} disabled={!ocrResult || targetLang === 'none' || isBusy}>
            {status.kind === 'loading' && status.action === 'translate'
              ? <><span className="spinner spinner-dark" />Translating…</>
              : 'Translate'}
          </button>
          <span className="ocr-footer-divider" />
          <button className="copy-to-word-btn" onClick={handleCopyToWord} disabled={!displayResult || isBusy}>
            {status.kind === 'loading' && status.action === 'clipboard'
              ? <><span className="spinner spinner-dark" />Converting…</>
              : 'Copy to Word Clipboard'}
          </button>
          <button className="export-docx-btn" onClick={handleExportDocx} disabled={!displayResult || isBusy}>
            {status.kind === 'loading' && status.action === 'docx'
              ? <><span className="spinner spinner-dark" />Exporting…</>
              : 'Export .docx'}
          </button>
        </div>
        <div className="ocr-footer-status">
          {status.kind === 'ok'    && <span className="to-word-status ok">✓ {status.message}</span>}
          {status.kind === 'error' && <span className="to-word-status error">✗ {status.message}</span>}
        </div>
      </div>

    </div>
  );
}
