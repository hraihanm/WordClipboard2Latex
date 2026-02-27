import { useCallback, useEffect, useRef, useState } from 'react';
import { ocrImage, toClipboard, exportDocx, translateText, addHistory, type HistoryItem } from '../api';
import CodeOutput from './CodeOutput';
import CopyButton from './CopyButton';
import Preview from './Preview';
import Select from './Select';
import HistoryPanel from './HistoryPanel';

function makeTitle(text: string): string {
  return text.replace(/^\$\$[\s\S]*?\$\$/gm, '[equation]').replace(/\$[^$]+\$/g, '[math]')
    .replace(/^#+\s*/gm, '').trim().split('\n')[0].slice(0, 70) || 'OCR Result';
}

function generateThumbnail(blob: Blob, maxWidth = 220): Promise<string> {
  return new Promise((resolve) => {
    const img = new Image();
    const url = URL.createObjectURL(blob);
    img.onload = () => {
      const scale = Math.min(1, maxWidth / img.width);
      const canvas = document.createElement('canvas');
      canvas.width  = Math.round(img.width  * scale);
      canvas.height = Math.round(img.height * scale);
      canvas.getContext('2d')!.drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      resolve(canvas.toDataURL('image/jpeg', 0.72));
    };
    img.src = url;
  });
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result as string);
    r.onerror = reject;
    r.readAsDataURL(blob);
  });
}

type Backend    = 'gemini' | 'got' | 'texify';
type Format     = 'markdown' | 'latex';
type LangOption = 'none' | 'English' | 'Indonesian';
type Rect       = { x: number; y: number; w: number; h: number };

type ActionStatus =
  | { kind: 'idle' }
  | { kind: 'loading'; action: 'ocr' | 'translate' | 'clipboard' | 'docx' }
  | { kind: 'ok';    message: string }
  | { kind: 'error'; message: string };

const BACKEND_OPTIONS = [
  { value: 'gemini',  label: 'Gemini Flash' },
  { value: 'got',     label: 'GOT-OCR (local)' },
  { value: 'texify',  label: 'texify (equations)' },
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

  const [status, setStatus]   = useState<ActionStatus>({ kind: 'idle' });
  const [dragging, setDragging] = useState(false);
  const [historyKey, setHistoryKey] = useState(0);
  const [debugInfo, setDebugInfo] = useState<{
    backend: Backend;
    format: Format;
    imageSize?: number;
    imageType?: string;
    cropRect?: Rect | null;
    durationMs?: number;
    resultLength?: number;
    error?: string;
  } | null>(null);
  const [debugLogs, setDebugLogs] = useState<Array<{ step: string; msg: string; elapsed_ms: number }>>([]);
  const [debugOpen, setDebugOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const ocrAbortRef = useRef<AbortController | null>(null);

  // ── Crop selection (texify mode) ──────────────────────────
  const imgRef          = useRef<HTMLImageElement>(null);
  const cropStartRef    = useRef<{ x: number; y: number } | null>(null);
  const [cropRect, setCropRect]         = useState<Rect | null>(null);
  const [cropDragging, setCropDragging] = useState(false);

  const isBusy     = status.kind === 'loading';
  const cropReady  = cropRect !== null && cropRect.w > 5 && cropRect.h > 5;

  const cancelOcr = useCallback(() => {
    ocrAbortRef.current?.abort();
  }, []);

  const handleRestore = (item: HistoryItem) => {
    const d = item.data as { result: string; format: Format; backend: Backend };
    setOcrResult(d.result);
    setDisplayResult(d.result);
    setFormat(d.format ?? 'markdown');
    setBackend(d.backend ?? 'gemini');
    setIsTranslated(false);
    setStatus({ kind: 'idle' });
    setCropRect(null);
    if (item.image || item.thumbnail) {
      const url = item.image ?? item.thumbnail!;
      setImageUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return url; });
      setImage(null);
    }
  };

  // ── Image loading ──────────────────────────────────────────
  const loadImage = useCallback((blob: File | Blob) => {
    setImage(blob);
    setOcrResult(null);
    setDisplayResult(null);
    setIsTranslated(false);
    setStatus({ kind: 'idle' });
    setCropRect(null);
    setDebugInfo(null);
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

  // Escape clears crop selection
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && cropRect) setCropRect(null);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [cropRect]);

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
    setCropRect(null);
    setDebugInfo(null);
    setStatus({ kind: 'idle' });
  };

  // ── Crop mouse handlers ────────────────────────────────────
  const handleCropMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (isBusy) return;
    e.preventDefault();
    const rect = e.currentTarget.getBoundingClientRect();
    cropStartRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    setCropRect(null);
    setCropDragging(true);
  };

  const handleCropMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!cropDragging || !cropStartRef.current) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
    const y = Math.max(0, Math.min(e.clientY - rect.top, rect.height));
    const s = cropStartRef.current;
    setCropRect({ x: Math.min(x, s.x), y: Math.min(y, s.y), w: Math.abs(x - s.x), h: Math.abs(y - s.y) });
  };

  const handleCropMouseUp = () => {
    setCropDragging(false);
    cropStartRef.current = null;
  };

  // ── Crop the image and return a blob ──────────────────────
  const getCroppedBlob = async (): Promise<Blob | null> => {
    if (!cropRect || !imgRef.current) return null;
    if (cropRect.w < 5 || cropRect.h < 5) return null;
    const img = imgRef.current;

    // object-fit: contain may letterbox; compute actual rendered image rect
    const dW = img.offsetWidth,  dH = img.offsetHeight;
    const nW = img.naturalWidth, nH = img.naturalHeight;
    const scale   = Math.min(dW / nW, dH / nH);
    const rW      = nW * scale, rH = nH * scale;
    const offX    = (dW - rW) / 2, offY = (dH - rH) / 2;

    const srcX = Math.max(0, Math.round((cropRect.x - offX) / scale));
    const srcY = Math.max(0, Math.round((cropRect.y - offY) / scale));
    const srcW = Math.min(nW - srcX, Math.round(cropRect.w / scale));
    const srcH = Math.min(nH - srcY, Math.round(cropRect.h / scale));
    if (srcW < 1 || srcH < 1) return null;

    const canvas = document.createElement('canvas');
    canvas.width = srcW; canvas.height = srcH;
    canvas.getContext('2d')!.drawImage(img, srcX, srcY, srcW, srcH, 0, 0, srcW, srcH);
    return new Promise((resolve) => canvas.toBlob((b) => resolve(b), 'image/png'));
  };

  // ── Actions ───────────────────────────────────────────────
  const handleOcr = async () => {
    if (!image) return;
    setStatus({ kind: 'loading', action: 'ocr' });
    setOcrResult(null); setDisplayResult(null); setIsTranslated(false);
    setDebugLogs([{ step: 'client', msg: 'Sending request to backend…', elapsed_ms: 0 }]);
    setDebugOpen(true);
    const start = performance.now();
    const imageSize = image.size;
    const imageType = image.type || 'unknown';
    ocrAbortRef.current = new AbortController();
    try {
      let imageToOcr: File | Blob = image;
      if (backend === 'texify' && cropReady) {
        const cropped = await getCroppedBlob();
        if (cropped) imageToOcr = cropped;
      }
      const res = await ocrImage(imageToOcr, backend, format, {
        signal: ocrAbortRef.current.signal,
        onLog: (entry) => setDebugLogs((prev) => [...prev, entry]),
      });
      const durationMs = Math.round(performance.now() - start);
      setOcrResult(res.result);
      setDisplayResult(res.result);
      setStatus({ kind: 'idle' });
      setDebugInfo({
        backend,
        format,
        imageSize,
        imageType,
        cropRect: backend === 'texify' ? cropRect : null,
        durationMs,
        resultLength: res.result.length,
      });
      setDebugOpen(true);
      const [thumb, fullImage] = await Promise.all([
        generateThumbnail(image),
        blobToDataUrl(image),
      ]);
      await addHistory('ocr', makeTitle(res.result), { result: res.result, format, backend }, thumb, fullImage);
      setHistoryKey((k) => k + 1);
    } catch (err) {
      const durationMs = Math.round(performance.now() - start);
      const errMsg = err instanceof Error ? err.message : 'OCR failed';
      const isAborted = err instanceof Error && err.name === 'AbortError';
      setStatus({ kind: 'error', message: isAborted ? 'Cancelled' : errMsg });
      setDebugInfo({
        backend,
        format,
        imageSize,
        imageType,
        cropRect: backend === 'texify' ? cropRect : null,
        durationMs,
        error: isAborted ? 'Cancelled' : errMsg,
      });
      setDebugOpen(true);
    } finally {
      ocrAbortRef.current = null;
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

  // ── Render ────────────────────────────────────────────────
  return (
    <div className="ocr-panel">

      {/* ── Row 0: Controls ── */}
      <div className="ocr-controls">
        <div className="ocr-selects">
          <label className="ocr-label">Backend</label>
          <Select
            value={backend}
            options={BACKEND_OPTIONS}
            onChange={(v) => {
              setBackend(v as Backend);
              if (v === 'texify') setFormat('latex');
              setCropRect(null);
            }}
            disabled={isBusy}
          />
          {backend !== 'texify' ? (
            <>
              <label className="ocr-label">Output</label>
              <Select
                value={format} options={FORMAT_OPTIONS}
                onChange={(v) => { setFormat(v as Format); setOcrResult(null); setDisplayResult(null); setIsTranslated(false); }}
                disabled={isBusy}
              />
            </>
          ) : (
            <span className="ocr-texify-badge">LaTeX only · drag to select equation</span>
          )}
          <label className="ocr-label">Translate to</label>
          <Select
            value={targetLang} options={LANG_OPTIONS}
            onChange={(v) => { setTargetLang(v as LangOption); setStatus({ kind: 'idle' }); }}
            disabled={isBusy}
          />
        </div>
        <div className="ocr-run-group">
          <button className="convert-btn" onClick={handleOcr} disabled={!image || isBusy}>
            {status.kind === 'loading' && status.action === 'ocr' && <span className="spinner" />}
            {status.kind === 'loading' && status.action === 'ocr'
              ? 'Running OCR…'
              : backend === 'texify' && cropReady
                ? 'OCR Selection'
                : 'Run OCR'}
          </button>
          {status.kind === 'loading' && status.action === 'ocr' && (
            <button type="button" className="ocr-cancel-btn" onClick={cancelOcr} title="Cancel OCR">
              Cancel
            </button>
          )}
        </div>
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
              <div className="ocr-img-wrapper">
                <img ref={imgRef} src={imageUrl} alt="Input" className="ocr-preview-img" draggable={false} />
                {backend === 'texify' && (
                  <>
                    <div className={`ocr-crop-hint${cropReady ? ' crop-ready' : ''}`}>
                      {cropReady
                        ? 'Selection ready — click Run OCR, or drag to redraw · Esc to clear'
                        : 'Drag to select equation region · Esc to clear'}
                    </div>
                    <div
                      className={`ocr-crop-overlay${cropDragging ? ' cropping' : ''}`}
                      onMouseDown={handleCropMouseDown}
                      onMouseMove={handleCropMouseMove}
                      onMouseUp={handleCropMouseUp}
                      onMouseLeave={handleCropMouseUp}
                    >
                      {cropRect && cropRect.w > 2 && cropRect.h > 2 && (
                        <div
                          className="ocr-crop-selection"
                          style={{ left: cropRect.x, top: cropRect.y, width: cropRect.w, height: cropRect.h }}
                        />
                      )}
                    </div>
                  </>
                )}
              </div>
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

      <HistoryPanel tab="ocr" refreshKey={historyKey} onRestore={handleRestore} />

      {(image || debugInfo) && (
        <details
          className="debug-section"
          open={debugOpen}
          onToggle={(e) => setDebugOpen((e.target as HTMLDetailsElement).open)}
          style={{ marginTop: '1.5rem' }}
        >
          <summary>OCR Debug Info</summary>
          <div className="debug-content">
            {image && (
              <div className="debug-formats">
                <h4>Current State</h4>
                <table className="debug-table">
                  <tbody>
                    <tr><td>Backend</td><td>{backend}</td></tr>
                    <tr><td>Format</td><td>{format}</td></tr>
                    <tr><td>Target language</td><td>{targetLang}</td></tr>
                    <tr><td>Image size</td><td>{image.size.toLocaleString()} bytes</td></tr>
                    <tr><td>Image type</td><td>{image.type || 'unknown'}</td></tr>
                    {backend === 'texify' && cropRect && (
                      <tr><td>Crop rect</td><td>x={cropRect.x} y={cropRect.y} w={cropRect.w} h={cropRect.h}</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}
            {debugInfo && (
              <div className="debug-raw">
                <h4>Last OCR Run</h4>
                <table className="debug-table">
                  <tbody>
                    <tr><td>Backend</td><td>{debugInfo.backend}</td></tr>
                    <tr><td>Format</td><td>{debugInfo.format}</td></tr>
                    {debugInfo.imageSize != null && (
                      <tr><td>Image size</td><td>{debugInfo.imageSize.toLocaleString()} bytes</td></tr>
                    )}
                    {debugInfo.durationMs != null && (
                      <tr><td>Duration</td><td>{debugInfo.durationMs} ms</td></tr>
                    )}
                    {debugInfo.resultLength != null && (
                      <tr><td>Result length</td><td>{debugInfo.resultLength} chars</td></tr>
                    )}
                    {debugInfo.error && (
                      <tr><td>Error</td><td className="status-warn">{debugInfo.error}</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}
            {(debugLogs.length > 0 || (status.kind === 'loading' && status.action === 'ocr')) && (
              <div className="debug-logs">
                <h4>Process Log (live)</h4>
                <div className="debug-logs-list">
                  {debugLogs.map((log, i) => (
                    <div key={i} className="debug-log-entry">
                      <span className="debug-log-time">+{log.elapsed_ms} ms</span>
                      <span className="debug-log-step">{log.step}</span>
                      <span className="debug-log-msg">{log.msg}</span>
                    </div>
                  ))}
                  {status.kind === 'loading' && status.action === 'ocr' && debugLogs.length === 0 && (
                    <div className="debug-log-entry debug-log-pending">
                      <span className="debug-log-msg">Waiting for backend…</span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </details>
      )}

    </div>
  );
}
