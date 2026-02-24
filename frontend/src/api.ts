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

export interface OcrResult {
  result: string;
  backend: string;
}

export async function ocrImage(
  image: File | Blob,
  backend: 'gemini' | 'got',
  format: 'latex' | 'markdown' | 'text',
): Promise<OcrResult> {
  const form = new FormData();
  form.append('image', image instanceof File ? image : new File([image], 'paste.png', { type: 'image/png' }));
  form.append('backend', backend);
  form.append('format', format);
  const res = await fetch('/api/ocr', { method: 'POST', body: form });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Server error: ${res.status}`);
  }
  return res.json();
}

export async function clipboardInfo(): Promise<ClipboardInfo> {
  const res = await fetch('/api/clipboard-info');
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Server error: ${res.status}`);
  }
  return res.json();
}
