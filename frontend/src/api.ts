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
  /** Inner HTML of &lt;body&gt; from CF_HTML (no head / wrapper). */
  raw_html_body: string;
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
  lmstudio_base_url: string;
  lmstudio_model: string;
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

// ── Quiz conversion ──────────────────────────────────────────
export interface QuizQuestionData {
  number: number;
  stem: string;
  options: string[];
  answer_label: string;
  solution_body: string;
}

export interface QuizResult {
  quiz_markdown: string;
  question_count: number;
  questions: QuizQuestionData[];
  warnings: string[];
  preset: string;
}

export interface QuizToWordResult {
  question_count: number;
  formats_written: string[];
  warnings: string[];
}

export async function quizToClipboard(text: string): Promise<QuizToWordResult> {
  const res = await fetch('/api/quiz/to-clipboard', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Server error: ${res.status}`);
  }
  return res.json();
}

export interface QuizToDocxOptions {
  includeSolutions?: boolean;
  useTemplate?: boolean;
  /** Append the hidden BANK_META line after each solution. Off by default. */
  includeMeta?: boolean;
  filename?: string;
  /** Optional uploaded .docx whose named styles override the bundled template. */
  templateFile?: File | null;
}

export async function quizToDocx(text: string, opts: QuizToDocxOptions = {}): Promise<void> {
  const {
    includeSolutions = true,
    useTemplate = true,
    includeMeta = false,
    filename = 'quiz',
    templateFile = null,
  } = opts;
  const fd = new FormData();
  fd.append('text', text);
  fd.append('include_solutions', String(includeSolutions));
  fd.append('use_template', String(useTemplate));
  fd.append('include_meta', String(includeMeta));
  fd.append('filename', filename);
  if (templateFile) fd.append('template', templateFile, templateFile.name);
  const res = await fetch('/api/quiz/to-docx', {
    method: 'POST',
    body: fd, // browser sets multipart/form-data + boundary
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Server error: ${res.status}`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  // Prefer the server's Content-Disposition filename; fall back to the request.
  const cd = res.headers.get('Content-Disposition') || '';
  const m = cd.match(/filename="?([^"]+)"?/i);
  a.download = m ? m[1] : `${filename || 'quiz'}.docx`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function convertQuiz(preset: 'astro_dev_id' | 'generic' = 'astro_dev_id'): Promise<QuizResult> {
  const res = await fetch(`/api/convert/quiz?preset=${preset}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Server error: ${res.status}`);
  }
  return res.json();
}

export async function convertQuizText(html: string, preset: 'astro_dev_id' | 'generic' = 'astro_dev_id'): Promise<QuizResult> {
  const res = await fetch('/api/convert/quiz', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ html, preset }),
  });
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
