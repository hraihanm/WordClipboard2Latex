export interface ConvertResult {
  latex: string;
  markdown: string;
  html: string;
  warnings: string[];
}

export interface HealthResult {
  status: string;
  pandoc_installed: boolean;
  pandoc_version: string | null;
}

export async function convertClipboard(): Promise<ConvertResult> {
  const res = await fetch('/api/convert');
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Server error: ${res.status}`);
  }
  return res.json();
}

export async function convertText(html: string): Promise<ConvertResult> {
  const res = await fetch('/api/convert/text', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ html }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Server error: ${res.status}`);
  }
  return res.json();
}

export async function healthCheck(): Promise<HealthResult> {
  const res = await fetch('/api/health');
  return res.json();
}

export interface ClipboardFormat {
  id: number;
  name: string;
}

export interface ClipboardInfo {
  formats: ClipboardFormat[];
  has_html: boolean;
  raw_html: string;
  plain_text: string;
  error?: string;
}

export interface ToClipboardResult {
  formats_written: string[];
  warnings: string[];
}

export async function toClipboard(
  text: string,
  format: 'markdown' | 'latex',
): Promise<ToClipboardResult> {
  const res = await fetch('/api/to-clipboard', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, format }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Server error: ${res.status}`);
  }
  return res.json();
}

// ── History ──────────────────────────────────────────────────
export interface HistoryItem {
  id: number;
  tab: string;
  created_at: string;
  title: string;
  thumbnail?: string;
  image?: string;
  data: Record<string, unknown>;
}

export async function getHistory(tab: string): Promise<HistoryItem[]> {
  const res = await fetch(`/api/history/${tab}`);
  const body = await res.json();
  return body.items ?? [];
}

export async function addHistory(
  tab: string,
  title: string,
  data: Record<string, unknown>,
  thumbnail?: string,
  image?: string,
): Promise<number> {
  const res = await fetch('/api/history', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tab, title, data, thumbnail, image }),
  });
  return (await res.json()).id;
}

export async function deleteHistoryItem(id: number): Promise<void> {
  const res = await fetch(`/api/history/item/${id}`, { method: 'DELETE' });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Delete failed: ${res.status}`);
  }
}

export async function clearHistory(tab: string): Promise<void> {
  await fetch(`/api/history/tab/${tab}`, { method: 'DELETE' });
}

export interface OcrResult {
  result: string;
  backend: string;
}

export interface OcrLogEntry {
  step: string;
  msg: string;
  elapsed_ms: number;
}

export interface OcrImageOptions {
  signal?: AbortSignal;
  onLog?: (entry: OcrLogEntry) => void;
}

export async function ocrImage(
  image: File | Blob,
  backend: 'gemini' | 'ollama' | 'got' | 'texify',
  format: 'latex' | 'markdown' | 'text',
  options?: OcrImageOptions,
): Promise<OcrResult> {
  const form = new FormData();
  form.append('image', image instanceof File ? image : new File([image], 'paste.png', { type: 'image/png' }));
  form.append('backend', backend);
  form.append('format', format);
  form.append('stream', 'true');
  const res = await fetch('/api/ocr', {
    method: 'POST',
    body: form,
    signal: options?.signal,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Server error: ${res.status}`);
  }
  if (res.headers.get('content-type')?.includes('text/event-stream')) {
    return parseOcrStream(res, options?.onLog);
  }
  return res.json();
}

async function parseOcrStream(
  res: Response,
  onLog?: (entry: OcrLogEntry) => void,
): Promise<OcrResult> {
  const reader = res.body?.getReader();
  const decoder = new TextDecoder();
  if (!reader) throw new Error('No response body');
  let buffer = '';
  let result: OcrResult | null = null;
  let error: string | null = null;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split(/\n\n+/);
    buffer = blocks.pop() ?? '';
    for (const block of blocks) {
      let eventType = '';
      let data = '';
      for (const line of block.split('\n')) {
        if (line.startsWith('event: ')) eventType = line.slice(7).trim();
        else if (line.startsWith('data: ')) data = line.slice(6);
      }
      if (!data) continue;
      if (eventType === 'log' && onLog) {
        try {
          onLog(JSON.parse(data) as OcrLogEntry);
        } catch {
          /* ignore */
        }
      } else if (eventType === 'result') {
        try {
          result = JSON.parse(data) as OcrResult;
        } catch {
          /* ignore */
        }
      } else if (eventType === 'error') {
        try {
          const err = JSON.parse(data) as { error?: string };
          error = err.error ?? 'OCR failed';
        } catch {
          error = 'OCR failed';
        }
      }
    }
  }
  if (error) throw new Error(error);
  if (!result) throw new Error('No result from OCR stream');
  return result;
}

export async function translateText(
  text: string,
  targetLanguage: string,
  format: 'markdown' | 'latex',
): Promise<string> {
  const res = await fetch('/api/translate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, target_language: targetLanguage, format }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Server error: ${res.status}`);
  }
  const data = await res.json();
  return data.result;
}

export async function exportDocx(text: string, format: 'markdown' | 'latex'): Promise<void> {
  const res = await fetch('/api/export/docx', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, format }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Server error: ${res.status}`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'output.docx';
  a.click();
  URL.revokeObjectURL(url);
}

export interface AppSettings {
  ollama_base_url: string;
  ollama_model: string;
  gemini_api_key?: string;
}

export async function getSettings(): Promise<AppSettings> {
  const res = await fetch('/api/settings');
  if (!res.ok) throw new Error(`Settings: ${res.status}`);
  return res.json();
}

export async function updateSettings(updates: Partial<AppSettings>): Promise<void> {
  const res = await fetch('/api/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error(`Settings update failed: ${res.status}`);
}

export async function clipboardInfo(): Promise<ClipboardInfo> {
  const res = await fetch('/api/clipboard-info');
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Server error: ${res.status}`);
  }
  return res.json();
}
