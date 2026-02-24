import { useCallback, useEffect, useRef, useState } from 'react';
import { ocrImage } from '../api';
import CodeOutput from './CodeOutput';
import CopyButton from './CopyButton';

type Backend = 'gemini' | 'got';
type Format = 'latex' | 'markdown' | 'text';

const BACKEND_LABELS: Record<Backend, string> = {
  gemini: 'Gemini Flash',
  got:    'GOT-OCR (local)',
};

const FORMAT_LABELS: Record<Format, string> = {
  markdown: 'Markdown',
  latex:    'LaTeX',
  text:     'Plain Text',
};

const FORMAT_LANG: Record<Format, string> = {
  markdown: 'markdown',
  latex:    'latex',
  text:     'plaintext',
};

export default function OcrPanel() {
  const [image, setImage]       = useState<File | Blob | null>(null);
  const [preview, setPreview]   = useState<string | null>(null);
  const [backend, setBackend]   = useState<Backend>('gemini');
  const [format, setFormat]     = useState<Format>('markdown');
  const [result, setResult]     = useState<string | null>(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileInputRef            = useRef<HTMLInputElement>(null);
  const dropRef                 = useRef<HTMLDivElement>(null);

  // Accept a file/blob and generate a preview URL
  const loadImage = useCallback((blob: File | Blob) => {
    setImage(blob);
    setResult(null);
    setError(null);
    const url = URL.createObjectURL(blob);
    setPreview((prev) => { if (prev) URL.revokeObjectURL(prev); return url; });
  }, []);

  // Paste from clipboard (Ctrl+V anywhere on the page)
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

  // Drag & drop
  const onDragOver = (e: React.DragEvent) => { e.preventDefault(); setDragging(true); };
  const onDragLeave = () => setDragging(false);
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('image/')) loadImage(file);
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) loadImage(file);
    e.target.value = '';
  };

  const handleOcr = async () => {
    if (!image) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await ocrImage(image, backend, format);
      setResult(res.result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'OCR failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="ocr-panel">
      {/* Controls row */}
      <div className="ocr-controls">
        <div className="ocr-selects">
          <label className="ocr-label">Backend</label>
          <select
            className="ocr-select"
            value={backend}
            onChange={(e) => setBackend(e.target.value as Backend)}
          >
            {(Object.keys(BACKEND_LABELS) as Backend[]).map((b) => (
              <option key={b} value={b}>{BACKEND_LABELS[b]}</option>
            ))}
          </select>
          <label className="ocr-label">Output</label>
          <select
            className="ocr-select"
            value={format}
            onChange={(e) => setFormat(e.target.value as Format)}
          >
            {(Object.keys(FORMAT_LABELS) as Format[]).map((f) => (
              <option key={f} value={f}>{FORMAT_LABELS[f]}</option>
            ))}
          </select>
        </div>
        <button
          className="convert-btn"
          onClick={handleOcr}
          disabled={!image || loading}
        >
          {loading && <span className="spinner" />}
          {loading ? 'Running OCR…' : 'Run OCR'}
        </button>
      </div>

      <div className="ocr-body">
        {/* Drop zone */}
        <div
          ref={dropRef}
          className={`ocr-dropzone${dragging ? ' dragging' : ''}${preview ? ' has-image' : ''}`}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          onClick={() => !preview && fileInputRef.current?.click()}
        >
          {preview ? (
            <>
              <img src={preview} alt="Selected" className="ocr-preview-img" />
              <button
                className="ocr-clear-btn"
                onClick={(e) => { e.stopPropagation(); setImage(null); setPreview(null); setResult(null); }}
              >
                ✕
              </button>
            </>
          ) : (
            <div className="ocr-dropzone-hint">
              <span className="ocr-dropzone-icon">⬆</span>
              <span>Drop image, <strong>Ctrl+V</strong> to paste, or <span className="ocr-link" onClick={() => fileInputRef.current?.click()}>browse</span></span>
            </div>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            style={{ display: 'none' }}
            onChange={onFileChange}
          />
        </div>

        {/* Result panel */}
        <div className="ocr-result-panel">
          {error && (
            <div className="error-box" style={{ margin: '0 0 0.75rem' }}>{error}</div>
          )}
          {result !== null ? (
            <div className="output-panel" style={{ flex: 1 }}>
              <div className="panel-header">
                <span className="panel-label">Result</span>
                <CopyButton text={result} />
              </div>
              <CodeOutput content={result} language={FORMAT_LANG[format]} />
            </div>
          ) : (
            <div className="ocr-result-empty">
              {loading ? 'Processing…' : 'Result will appear here'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
