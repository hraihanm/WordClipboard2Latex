import { useRef, useState } from 'react';
import * as pdfjsLib from 'pdfjs-dist';
import { ocrImage, toClipboard, exportDocx, addHistory } from '../api';
import Preview from './Preview';
import CodeOutput from './CodeOutput';
import CopyButton from './CopyButton';
import Select from './Select';
import HistoryPanel from './HistoryPanel';

// Vite resolves this to the bundled worker file
pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

type Backend = 'gemini' | 'ollama' | 'lmstudio' | 'got';
type Format  = 'markdown' | 'latex';

type Status =
  | { kind: 'idle' }
  | { kind: 'rendering'; page: number; total: number }
  | { kind: 'ocr';       page: number; total: number }
  | { kind: 'ok';   message: string }
  | { kind: 'error'; message: string };

const BACKEND_OPTIONS = [
  { value: 'gemini',   label: 'Gemini Flash' },
  { value: 'ollama',   label: 'Ollama (local)' },
  { value: 'lmstudio', label: 'LM Studio (local)' },
  { value: 'got',      label: 'GOT-OCR (local)' },
];

const FORMAT_OPTIONS = [
  { value: 'markdown', label: 'Markdown' },
  { value: 'latex',    label: 'LaTeX' },
];

const PAGE_SEPARATOR = (n: number) => `\n\n---\n*Page ${n}*\n\n`;

/** Render a single PDF page to a PNG Blob at 2× scale for good OCR quality. */
async function renderPageToBlob(
  pdf: pdfjsLib.PDFDocumentProxy,
  pageNum: number,
): Promise<Blob> {
  const page     = await pdf.getPage(pageNum);
  const viewport = page.getViewport({ scale: 2.0 });
  const canvas   = document.createElement('canvas');
  canvas.width   = viewport.width;
  canvas.height  = viewport.height;
  await page.render({ canvasContext: canvas.getContext('2d')!, viewport }).promise;
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('canvas.toBlob failed'))), 'image/png'),
  );
}

/** Parse a page-range string like "1-3, 5, 7-9" into a sorted, deduplicated list of page numbers. */
function parsePageRange(raw: string, total: number): number[] {
  const pages = new Set<number>();
  for (const part of raw.split(',')) {
    const t = part.trim();
    const range = t.match(/^(\d+)\s*-\s*(\d+)$/);
    if (range) {
      const lo = Math.max(1, parseInt(range[1]));
      const hi = Math.min(total, parseInt(range[2]));
      for (let i = lo; i <= hi; i++) pages.add(i);
    } else if (/^\d+$/.test(t)) {
      const n = parseInt(t);
      if (n >= 1 && n <= total) pages.add(n);
    }
  }
  return [...pages].sort((a, b) => a - b);
}

export default function PdfPanel() {
  const [pdfFile, setPdfFile]       = useState<File | null>(null);
  const [pageCount, setPageCount]   = useState<number>(0);
  const [pageRange, setPageRange]   = useState('');
  const [backend, setBackend]       = useState<Backend>('gemini');
  const [format, setFormat]         = useState<Format>('markdown');
  const [result, setResult]         = useState<string | null>(null);
  const [status, setStatus]         = useState<Status>({ kind: 'idle' });
  const [dragging, setDragging]     = useState(false);
  const [historyKey, setHistoryKey] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortRef     = useRef<boolean>(false);

  const isBusy = status.kind === 'rendering' || status.kind === 'ocr';

  // ── File loading ─────────────────────────────────────────────────────────

  const loadPdf = async (file: File) => {
    if (!file.type.includes('pdf') && !file.name.endsWith('.pdf')) return;
    setPdfFile(file);
    setResult(null);
    setStatus({ kind: 'idle' });
    setPageRange('');
    try {
      const buf  = await file.arrayBuffer();
      const pdf  = await pdfjsLib.getDocument({ data: buf }).promise;
      setPageCount(pdf.numPages);
    } catch {
      setStatus({ kind: 'error', message: 'Failed to read PDF — is it valid?' });
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) loadPdf(f);
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (f) loadPdf(f); e.target.value = '';
  };

  // ── Main OCR run ──────────────────────────────────────────────────────────

  const handleRun = async () => {
    if (!pdfFile || pageCount === 0) return;
    abortRef.current = false;

    const pages = pageRange.trim()
      ? parsePageRange(pageRange, pageCount)
      : Array.from({ length: pageCount }, (_, i) => i + 1);

    if (pages.length === 0) {
      setStatus({ kind: 'error', message: 'Page range is empty or out of bounds.' });
      return;
    }

    const buf = await pdfFile.arrayBuffer();
    const pdf = await pdfjsLib.getDocument({ data: buf }).promise;

    const parts: string[] = [];
    setResult(null);

    for (let i = 0; i < pages.length; i++) {
      if (abortRef.current) break;

      const pageNum = pages[i];

      setStatus({ kind: 'rendering', page: pageNum, total: pages.length });
      let blob: Blob;
      try {
        blob = await renderPageToBlob(pdf, pageNum);
      } catch (err) {
        setStatus({ kind: 'error', message: `Failed to render page ${pageNum}: ${err}` });
        return;
      }

      setStatus({ kind: 'ocr', page: pageNum, total: pages.length });
      try {
        const res = await ocrImage(blob, backend as never, format);
        const text = pages.length > 1 ? PAGE_SEPARATOR(pageNum) + res.result : res.result;
        parts.push(text);
        setResult(parts.join(''));
      } catch (err) {
        setStatus({ kind: 'error', message: `Page ${pageNum} OCR failed: ${err instanceof Error ? err.message : err}` });
        return;
      }
    }

    if (abortRef.current) {
      setStatus({ kind: 'idle' });
      return;
    }

    const combined = parts.join('');
    setResult(combined);
    setStatus({ kind: 'ok', message: `${pages.length} page${pages.length > 1 ? 's' : ''} processed` });

    const title = pdfFile.name.replace(/\.pdf$/i, '').slice(0, 70) || 'PDF OCR';
    await addHistory('pdf', title, { result: combined, format, backend, pages: pages.length });
    setHistoryKey((k) => k + 1);
  };

  const handleCancel = () => { abortRef.current = true; };

  const handleCopyToWord = async () => {
    if (!result) return;
    setStatus({ kind: 'ocr', page: 0, total: 0 }); // reuse loading state
    try {
      await toClipboard(result, format);
      setStatus({ kind: 'ok', message: 'Copied to clipboard — paste into Word' });
    } catch (err) {
      setStatus({ kind: 'error', message: err instanceof Error ? err.message : 'Failed' });
    }
  };

  const handleExportDocx = async () => {
    if (!result) return;
    try {
      await exportDocx(result, format);
      setStatus({ kind: 'ok', message: 'output.docx downloaded' });
    } catch (err) {
      setStatus({ kind: 'error', message: err instanceof Error ? err.message : 'Failed' });
    }
  };

  // ── Status label ─────────────────────────────────────────────────────────

  const statusLabel = () => {
    if (status.kind === 'rendering') return `Rendering page ${status.page} / ${status.total}…`;
    if (status.kind === 'ocr' && status.total > 0) return `OCR page ${status.page} / ${status.total}…`;
    if (status.kind === 'ocr') return 'Processing…';
    return null;
  };

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="ocr-panel">

      {/* Controls */}
      <div className="ocr-controls">
        <div className="ocr-selects">
          <label className="ocr-label">Backend</label>
          <Select
            value={backend}
            options={BACKEND_OPTIONS}
            onChange={(v) => setBackend(v as Backend)}
            disabled={isBusy}
          />
          <label className="ocr-label">Output</label>
          <Select
            value={format}
            options={FORMAT_OPTIONS}
            onChange={(v) => setFormat(v as Format)}
            disabled={isBusy}
          />
          {pageCount > 0 && (
            <>
              <label className="ocr-label">Pages</label>
              <input
                className="pdf-page-range"
                type="text"
                placeholder={`1–${pageCount} (all)`}
                value={pageRange}
                onChange={(e) => setPageRange(e.target.value)}
                disabled={isBusy}
                title="e.g. 1-3, 5, 8-10"
              />
              <span className="ocr-label" style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>
                of {pageCount}
              </span>
            </>
          )}
        </div>
        <div className="ocr-run-group">
          <button className="convert-btn" onClick={handleRun} disabled={!pdfFile || isBusy}>
            {isBusy && <span className="spinner" />}
            {isBusy ? statusLabel() : 'Run OCR'}
          </button>
          {isBusy && (
            <button type="button" className="ocr-cancel-btn" onClick={handleCancel}>
              Cancel
            </button>
          )}
        </div>
      </div>

      {/* Body: drop zone | preview */}
      <div className="ocr-row-top">

        {/* Drop zone */}
        <div
          className={`ocr-dropzone${dragging ? ' dragging' : ''}${pdfFile ? ' has-image' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => !pdfFile && fileInputRef.current?.click()}
        >
          {pdfFile ? (
            <div className="pdf-info">
              <div className="pdf-icon">PDF</div>
              <div className="pdf-meta">
                <div className="pdf-name">{pdfFile.name}</div>
                <div className="pdf-pages">{pageCount} page{pageCount !== 1 ? 's' : ''}</div>
              </div>
              <button
                className="ocr-clear-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  setPdfFile(null); setPageCount(0); setResult(null);
                  setStatus({ kind: 'idle' }); setPageRange('');
                }}
                title="Remove"
              >
                ✕
              </button>
            </div>
          ) : (
            <div className="ocr-dropzone-hint">
              <span className="ocr-dropzone-icon">PDF</span>
              <span>Drop PDF here or <span className="ocr-link" onClick={() => fileInputRef.current?.click()}>browse</span></span>
              <span className="ocr-dropzone-sub">Each page is sent to the selected OCR backend</span>
            </div>
          )}
          <input ref={fileInputRef} type="file" accept="application/pdf" style={{ display: 'none' }} onChange={onFileChange} />
        </div>

        {/* Preview */}
        <div className="ocr-preview-zone">
          <div className="ocr-zone-header">
            <span className="panel-label">Preview</span>
          </div>
          <div className="ocr-preview-scroll">
            {result
              ? <Preview content={result} mode={format} />
              : <span className="ocr-zone-empty">
                  {isBusy ? statusLabel() : 'Preview will appear here'}
                </span>
            }
          </div>
        </div>

      </div>

      {/* Code output */}
      <div className="ocr-row-code">
        <div className="ocr-zone-header">
          <span className="panel-label">Code</span>
          <CopyButton text={result ?? ''} />
        </div>
        <div className="ocr-code-scroll">
          {result
            ? <CodeOutput content={result} language={format} />
            : <span className="ocr-zone-empty">
                {isBusy ? statusLabel() : 'Generated code will appear here'}
              </span>
          }
        </div>
      </div>

      {/* Footer */}
      <div className="ocr-footer">
        <div className="ocr-footer-actions">
          <button className="copy-to-word-btn" onClick={handleCopyToWord} disabled={!result || isBusy}>
            Copy to Word Clipboard
          </button>
          <button className="export-docx-btn" onClick={handleExportDocx} disabled={!result || isBusy}>
            Export .docx
          </button>
        </div>
        <div className="ocr-footer-status">
          {status.kind === 'ok'    && <span className="to-word-status ok">✓ {status.message}</span>}
          {status.kind === 'error' && <span className="to-word-status error">✗ {status.message}</span>}
        </div>
      </div>

      <HistoryPanel
        tab="pdf"
        refreshKey={historyKey}
        onRestore={(item) => {
          const d = item.data as { result: string; format: Format; backend: Backend };
          setResult(d.result ?? null);
          setFormat(d.format ?? 'markdown');
          setBackend(d.backend ?? 'gemini');
          setStatus({ kind: 'idle' });
        }}
      />

    </div>
  );
}
