import { useCallback, useEffect, useRef, useState } from 'react';
import { ocrImage, toClipboard, exportDocx } from '../api';
import CodeOutput from './CodeOutput';
import CopyButton from './CopyButton';
import Preview from './Preview';

type Backend = 'gemini' | 'got';
type Format  = 'markdown' | 'latex';

type ExportStatus =
  | { kind: 'idle' }
  | { kind: 'loading'; action: 'clipboard' | 'docx' }
  | { kind: 'ok'; message: string }
  | { kind: 'error'; message: string };

const BACKEND_LABELS: Record<Backend, string> = {
  gemini: 'Gemini Flash',
  got:    'GOT-OCR (local)',
};

export default function OcrPanel() {
  const [image, setImage]         = useState<File | Blob | null>(null);
  const [imageUrl, setImageUrl]   = useState<string | null>(null);
  const [backend, setBackend]     = useState<Backend>('gemini');
  const [format, setFormat]       = useState<Format>('markdown');
  const [result, setResult]       = useState<string | null>(null);
  const [activeView, setActiveView] = useState<'code' | 'preview'>('preview');
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState<string | null>(null);
  const [dragging, setDragging]   = useState(false);
  const [exportStatus, setExportStatus] = useState<ExportStatus>({ kind: 'idle' });
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadImage = useCallback((blob: File | Blob) => {
    setImage(blob);
    setResult(null);
    setError(null);
    setExportStatus({ kind: 'idle' });
    setImageUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return URL.createObjectURL(blob); });
  }, []);

  // Ctrl+V paste anywhere on the page
  useEffect(() => {
    const handler = (e: ClipboardEvent) => {
      if (!e.clipboardData) return;
      const item = Array.from(e.clipboardData.items).find((i) => i.type.startsWith('image/'));
      if (!item) return;
      const blob = item.getAsFile();
      if (blob) loadImage(blob);
    };
    window.addEventListener('paste', handler);
    return () => window.removeEventListener('paste', handler);
  }, [loadImage]);

  const onDragOver  = (e: React.DragEvent) => { e.preventDefault(); setDragging(true); };
  const onDragLeave = () => setDragging(false);
  const onDrop      = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file?.type.startsWith('image/')) loadImage(file);
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) loadImage(file);
    e.target.value = '';
  };

  const clearImage = (e: React.MouseEvent) => {
    e.stopPropagation();
    setImage(null);
    setImageUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return null; });
    setResult(null);
    setError(null);
    setExportStatus({ kind: 'idle' });
  };

  const handleOcr = async () => {
    if (!image) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setExportStatus({ kind: 'idle' });
    try {
      const res = await ocrImage(image, backend, format);
      setResult(res.result);
      setActiveView('preview');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'OCR failed');
    } finally {
      setLoading(false);
    }
  };

  const handleCopyToWord = async () => {
    if (!result) return;
    setExportStatus({ kind: 'loading', action: 'clipboard' });
    try {
      await toClipboard(result, format);
      setExportStatus({ kind: 'ok', message: 'Copied to clipboard — paste into Word' });
    } catch (err) {
      setExportStatus({ kind: 'error', message: err instanceof Error ? err.message : 'Failed' });
    }
  };

  const handleExportDocx = async () => {
    if (!result) return;
    setExportStatus({ kind: 'loading', action: 'docx' });
    try {
      await exportDocx(result, format);
      setExportStatus({ kind: 'ok', message: 'output.docx downloaded' });
    } catch (err) {
      setExportStatus({ kind: 'error', message: err instanceof Error ? err.message : 'Failed' });
    }
  };

  const isExporting = exportStatus.kind === 'loading';

  return (
    <div className="ocr-panel">

      {/* ── Controls ── */}
      <div className="ocr-controls">
        <div className="ocr-selects">
          <label className="ocr-label">Backend</label>
          <select className="ocr-select" value={backend} onChange={(e) => setBackend(e.target.value as Backend)}>
            {(Object.keys(BACKEND_LABELS) as Backend[]).map((b) => (
              <option key={b} value={b}>{BACKEND_LABELS[b]}</option>
            ))}
          </select>
          <label className="ocr-label">Output</label>
          <select className="ocr-select" value={format} onChange={(e) => { setFormat(e.target.value as Format); setResult(null); }}>
            <option value="markdown">Markdown</option>
            <option value="latex">LaTeX</option>
          </select>
        </div>
        <button className="convert-btn" onClick={handleOcr} disabled={!image || loading}>
          {loading && <span className="spinner" />}
          {loading ? 'Running OCR…' : 'Run OCR'}
        </button>
      </div>

      {/* ── Main area ── */}
      <div className="ocr-main">

        {/* Left: image drop zone */}
        <div
          className={`ocr-dropzone${dragging ? ' dragging' : ''}${imageUrl ? ' has-image' : ''}`}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          onClick={() => !imageUrl && fileInputRef.current?.click()}
        >
          {imageUrl ? (
            <>
              <img src={imageUrl} alt="Selected" className="ocr-preview-img" />
              <button className="ocr-clear-btn" onClick={clearImage} title="Remove image">✕</button>
            </>
          ) : (
            <div className="ocr-dropzone-hint">
              <span className="ocr-dropzone-icon">⬆</span>
              <span>
                Drop image here or{' '}
                <span className="ocr-link" onClick={() => fileInputRef.current?.click()}>browse</span>
              </span>
              <span className="ocr-dropzone-sub">Ctrl+V to paste from clipboard</span>
            </div>
          )}
          <input ref={fileInputRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={onFileChange} />
        </div>

        {/* Right: output */}
        <div className="ocr-output">
          {error && <div className="error-box" style={{ margin: '0 0 0.75rem' }}>{error}</div>}

          {result !== null ? (
            <>
              {/* View toggle */}
              <div className="ocr-view-toggle">
                <button
                  className={`tab ${activeView === 'preview' ? 'active' : ''}`}
                  onClick={() => setActiveView('preview')}
                >Preview</button>
                <button
                  className={`tab ${activeView === 'code' ? 'active' : ''}`}
                  onClick={() => setActiveView('code')}
                >Code</button>
                <div className="ocr-view-copy">
                  <CopyButton text={result} />
                </div>
              </div>

              <div className="ocr-output-body">
                {activeView === 'preview' ? (
                  <div className="preview-wrapper" style={{ flex: 1 }}>
                    <Preview content={result} mode={format} />
                  </div>
                ) : (
                  <CodeOutput content={result} language={format} />
                )}
              </div>
            </>
          ) : (
            <div className="ocr-output-empty">
              {loading ? 'Processing…' : 'OCR result will appear here'}
            </div>
          )}
        </div>
      </div>

      {/* ── Footer: export actions ── */}
      <div className="ocr-footer">
        <div className="ocr-footer-actions">
          <button
            className="copy-to-word-btn"
            disabled={!result || isExporting}
            onClick={handleCopyToWord}
          >
            {exportStatus.kind === 'loading' && exportStatus.action === 'clipboard'
              ? <><span className="spinner spinner-dark" />Converting…</>
              : 'Copy to Word Clipboard'}
          </button>
          <button
            className="export-docx-btn"
            disabled={!result || isExporting}
            onClick={handleExportDocx}
          >
            {exportStatus.kind === 'loading' && exportStatus.action === 'docx'
              ? <><span className="spinner spinner-dark" />Exporting…</>
              : 'Export .docx'}
          </button>
        </div>

        <div className="ocr-footer-status">
          {exportStatus.kind === 'ok' && (
            <span className="to-word-status ok">✓ {exportStatus.message}</span>
          )}
          {exportStatus.kind === 'error' && (
            <span className="to-word-status error">✗ {exportStatus.message}</span>
          )}
        </div>
      </div>

    </div>
  );
}
