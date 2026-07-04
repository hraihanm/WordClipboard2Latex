import { useState } from 'react';
import {
  convertQuiz,
  quizToClipboard,
  quizToDocx,
  type QuizResult,
  type QuizQuestionData,
} from '../api';
import CopyButton from './CopyButton';
import Preview from './Preview';
import Toast from './Toast';

/** Preprocess quiz markdown so the Preview component renders it readably. */
function toPreviewMd(md: string): string {
  return md
    .replace(/<!--[\s\S]*?-->/g, '')                         // strip <!-- BANK_META --> etc.
    .replace(/^<solution_title[^>]*>\s*/gm, '#### ');        // <solution_title> → h4
}

const OPTION_LETTERS = 'ABCDE';

// ── Word → Markdown: question preview card ───────────────────────────────

function QuizCard({ q }: { q: QuizQuestionData }) {
  const [solutionOpen, setSolutionOpen] = useState(false);
  const correctIdx = OPTION_LETTERS.indexOf(q.answer_label.toUpperCase());

  return (
    <div className="quiz-card">
      <div className="quiz-card-number">#{q.number}</div>
      <div className="quiz-card-stem">{q.stem || <em>(empty stem)</em>}</div>

      {q.options.length > 0 && (
        <ol className="quiz-options">
          {q.options.map((opt, i) => (
            <li
              key={i}
              className={`quiz-option ${i === correctIdx ? 'quiz-option-correct' : ''}`}
            >
              <span className="quiz-option-letter">{OPTION_LETTERS[i] ?? i + 1}.</span>
              {opt}
            </li>
          ))}
        </ol>
      )}

      {(q.answer_label || q.solution_body) && (
        <div className="quiz-solution-area">
          {q.answer_label && (
            <span className="quiz-answer-badge">Jawaban: {q.answer_label}</span>
          )}
          {q.solution_body && (
            <button
              className="quiz-solution-toggle"
              onClick={() => setSolutionOpen((o) => !o)}
            >
              {solutionOpen ? 'Sembunyikan pembahasan ▲' : 'Lihat pembahasan ▼'}
            </button>
          )}
          {solutionOpen && q.solution_body && (
            <pre className="quiz-solution-body">{q.solution_body}</pre>
          )}
        </div>
      )}
    </div>
  );
}

// ── Demo source ──────────────────────────────────────────────────────────
const DEMO_MD = `\
## Sebuah bintang bersuhu $T = 2\\,T_\\odot$ dan berjari-jari $R = 3\\,R_\\odot$. Menurut hukum Stefan–Boltzmann $L = 4\\pi R^2 \\sigma T^4$, luminositasnya dalam satuan $L_\\odot$ adalah …

- (A) $L \\approx 48\\,L_\\odot$
- (B) $L \\approx 9\\,L_\\odot$
- (C) $L \\approx 144\\,L_\\odot$
- (D) $L \\approx 24\\,L_\\odot$

### Jawaban
C

### Pembahasan
Rasio luminositas hanya bergantung pada $R$ dan $T$:

$$
\\frac{L}{L_\\odot} = \\left(\\frac{R}{R_\\odot}\\right)^2 \\left(\\frac{T}{T_\\odot}\\right)^4 = 3^2 \\cdot 2^4 = 9 \\cdot 16 = \\boxed{144}
$$

\`\`\`meta
type: mc
difficulty: 2
cognitive: Applying
topics:
  - Fisika Bintang/Luminositas
\`\`\`

## Manakah pernyataan berikut yang **benar** mengenai bintang deret utama? (pilih semua yang sesuai)

- (A) Energi dihasilkan oleh fusi hidrogen menjadi helium di inti
- (B) Bintang bermassa besar memiliki umur deret utama lebih pendek
- (C) Tekanan meningkat ke arah luar untuk menopang gravitasi
- (D) Semakin panas fotosfer, semakin biru warna bintang

### Jawaban
A, B, D

### Pembahasan
A, B, dan D benar. C salah — kesetimbangan hidrostatik memberi $dP/dr < 0$, sehingga tekanan **berkurang** ke arah luar (bertambah ke arah pusat).

## Hukum pergeseran Wien $\\lambda_\\max T = b$ dengan $b = 2{,}898 \\times 10^6\\ \\mathrm{nm\\cdot K}$. Untuk Matahari ($T_\\odot = 5{,}778\\ \\mathrm{K}$), panjang gelombang puncaknya adalah {{1}} nm, yang berada pada warna {{2}}.

### Jawaban
1. [numerik:0.02] 501
2. [teks] hijau-kuning

### Pembahasan
$$
\\lambda_\\max = \\frac{2{,}898 \\times 10^6}{5{,}778} \\approx 501\\ \\mathrm{nm}
$$

Panjang gelombang ini jatuh di rentang hijau–kuning — tepat di tempat mata manusia paling sensitif.

## Jelaskan mengapa bintang bermassa besar memiliki umur deret utama yang jauh lebih pendek daripada bintang bermassa kecil, meskipun memiliki cadangan hidrogen yang lebih banyak.

### Pembahasan
Umur deret utama sebanding dengan bahan bakar dibagi laju pembakaran, $t_\\mathrm{MS} \\propto M/L$. Pada deret utama berlaku hubungan massa–luminositas $L \\propto M^{3{,}5}$, sehingga:

$$
t_\\mathrm{MS} \\propto \\frac{M}{M^{3{,}5}} = M^{-2{,}5}
$$

Artinya bintang masif membakar bahan bakarnya jauh lebih boros: luminositasnya melonjak dengan pangkat tinggi terhadap massa. Meski cadangan hidrogennya lebih besar, laju konsumsi yang jauh lebih tinggi itu mengalahkan tambahan bahan bakar — sehingga umurnya justru jauh lebih singkat.
`;

// ── Markdown → Word: to-word panel ──────────────────────────────────────

function ToWordSection() {
  const [text, setText]         = useState('');
  const [status, setStatus]     = useState<string | null>(null);
  const [error, setError]       = useState<string | null>(null);
  const [loadingCb, setLoadingCb] = useState(false);
  const [loadingDx, setLoadingDx] = useState(false);
  const [includeSolutions, setIncludeSolutions] = useState(true);
  const [useTemplate, setUseTemplate] = useState(true);
  const [filename, setFilename] = useState('quiz');
  const [templateFile, setTemplateFile] = useState<File | null>(null);

  const handleToClipboard = async () => {
    if (!text.trim()) return;
    setLoadingCb(true);
    setStatus(null);
    setError(null);
    try {
      const res = await quizToClipboard(text);
      setStatus(
        `Copied ${res.question_count} question${res.question_count !== 1 ? 's' : ''} to clipboard — paste into Word.`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed');
    } finally {
      setLoadingCb(false);
    }
  };

  const handleToDocx = async () => {
    if (!text.trim()) return;
    setLoadingDx(true);
    setStatus(null);
    setError(null);
    try {
      await quizToDocx(text, { includeSolutions, useTemplate, filename, templateFile });
      setStatus(`DOCX downloaded${includeSolutions ? '' : ' (worksheet — no solutions)'}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed');
    } finally {
      setLoadingDx(false);
    }
  };

  return (
    <div className="to-word-section">
      <h3 className="section-heading">Quiz Markdown → Word</h3>
      <p className="hint" style={{ marginBottom: '0.75rem' }}>
        Paste astro-dev-id quiz markdown below. <em>Copy to Clipboard</em> writes
        Word-styled HTML (P-Problem / P-Sub-problem / Solution classes) that you
        can paste directly into Word. <em>Download DOCX</em> uses Pandoc — math
        converts to native Word equations and paragraphs pick up the bundled
        styled template (or upload your own .docx template below).
      </p>

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '0.35rem' }}>
        <button
          className="btn-secondary"
          style={{ fontSize: '0.78rem', padding: '2px 10px' }}
          onClick={() => setText(DEMO_MD)}
        >
          Load demo
        </button>
      </div>
      <textarea
        className="code-output"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={'## Problem stem with $math$\n\n- (A) Option A\n- (B) Option B\n\n### Jawaban\nA\n\n### Pembahasan\nSolution body...'}
        rows={14}
        style={{ width: '100%', fontFamily: 'monospace', fontSize: '0.8rem', resize: 'vertical', marginBottom: '0.75rem' }}
      />

      <div
        style={{
          display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap',
          marginBottom: '0.55rem', fontSize: '0.82rem', color: 'var(--text-muted)',
        }}
      >
        <span style={{ fontWeight: 600 }}>DOCX options:</span>
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={includeSolutions}
            onChange={(e) => setIncludeSolutions(e.target.checked)}
          />
          Include solutions &amp; answer key
        </label>
        <label
          style={{
            display: 'flex', alignItems: 'center', gap: '0.3rem',
            cursor: templateFile ? 'not-allowed' : 'pointer', opacity: templateFile ? 0.5 : 1,
          }}
          title={templateFile ? 'Ignored while a custom template is uploaded' : undefined}
        >
          <input
            type="checkbox"
            checked={useTemplate}
            disabled={!!templateFile}
            onChange={(e) => setUseTemplate(e.target.checked)}
          />
          Styled template
        </label>
        <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
          Template:
          {templateFile ? (
            <>
              <span
                style={{ maxWidth: '10rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                title={templateFile.name}
              >
                {templateFile.name}
              </span>
              <button
                type="button"
                onClick={() => setTemplateFile(null)}
                title="Remove uploaded template"
                style={{
                  border: 'none', background: 'transparent', cursor: 'pointer',
                  color: 'var(--text-muted)', fontSize: '1rem', lineHeight: 1, padding: 0,
                }}
              >
                ×
              </button>
            </>
          ) : (
            <label
              className="btn-secondary"
              style={{ fontSize: '0.75rem', padding: '2px 8px', cursor: 'pointer', margin: 0 }}
            >
              Upload .docx…
              <input
                type="file"
                accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                style={{ display: 'none' }}
                onChange={(e) => setTemplateFile(e.target.files?.[0] ?? null)}
              />
            </label>
          )}
        </span>
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
          File name:
          <input
            type="text"
            value={filename}
            onChange={(e) => setFilename(e.target.value)}
            placeholder="quiz"
            style={{
              width: '9rem', fontSize: '0.8rem', padding: '2px 6px',
              border: '1px solid var(--border)', borderRadius: '4px',
              background: 'var(--bg)', color: 'var(--text)',
            }}
          />
          <span style={{ opacity: 0.7 }}>.docx</span>
        </label>
      </div>

      <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
        <button
          className="convert-btn"
          onClick={handleToClipboard}
          disabled={loadingCb || !text.trim()}
        >
          {loadingCb ? 'Copying…' : 'Copy to Word Clipboard'}
        </button>
        <button
          className="btn-secondary"
          onClick={handleToDocx}
          disabled={loadingDx || !text.trim()}
        >
          {loadingDx ? 'Generating…' : includeSolutions ? 'Download DOCX' : 'Download Worksheet'}
        </button>
      </div>

      {status && (
        <p style={{ marginTop: '0.6rem', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          ✓ {status}
        </p>
      )}
      {error && <Toast message={error} onDismiss={() => setError(null)} />}
    </div>
  );
}

// ── Main panel ───────────────────────────────────────────────────────────

export default function QuizPanel() {
  const [result, setResult]       = useState<QuizResult | null>(null);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState<string | null>(null);
  const [preset, setPreset]       = useState<'astro_dev_id' | 'generic'>('astro_dev_id');
  const [activeDir, setActiveDir] = useState<'word-to-md' | 'md-to-word'>('word-to-md');
  const [mdView, setMdView]       = useState<'raw' | 'rendered'>('raw');

  const handleConvert = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await convertQuiz(preset);
      setResult(data);
      if (data.warnings.length > 0) setError(data.warnings.join('\n'));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Conversion failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="clipboard-panel">
      {/* Direction toggle */}
      <div className="quiz-dir-toggle">
        <button
          className={`quiz-dir-btn ${activeDir === 'word-to-md' ? 'active' : ''}`}
          onClick={() => setActiveDir('word-to-md')}
        >
          Word → Markdown
        </button>
        <button
          className={`quiz-dir-btn ${activeDir === 'md-to-word' ? 'active' : ''}`}
          onClick={() => setActiveDir('md-to-word')}
        >
          Markdown → Word
        </button>
      </div>

      {activeDir === 'word-to-md' && (
        <>
          <div className="convert-section">
            <p className="hint">
              Copy quiz content from Word (needs <code>P-Problem</code>,{' '}
              <code>P-Sub-problem</code>, <code>Solution-Title</code>,{' '}
              <code>Solution</code> paragraph styles), then click Convert.
            </p>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
              <label style={{ fontSize: '0.85rem', fontWeight: 500 }}>
                Output preset:&nbsp;
                <select
                  value={preset}
                  onChange={(e) => setPreset(e.target.value as 'astro_dev_id' | 'generic')}
                  style={{ marginLeft: '0.25rem' }}
                >
                  <option value="astro_dev_id">astro-dev-id (## / ### / &lt;solution_title&gt;)</option>
                  <option value="generic">Generic MCQ (A/B/C/D/E)</option>
                </select>
              </label>

              <button
                className="convert-btn"
                onClick={handleConvert}
                disabled={loading}
              >
                {loading ? 'Converting…' : 'Convert Quiz from Clipboard'}
              </button>
            </div>
          </div>

          {error && <Toast message={error} onDismiss={() => setError(null)} />}

          {result && (
            <>
              <div className="quiz-summary">
                {result.question_count} question{result.question_count !== 1 ? 's' : ''} parsed
                {' · '}preset: <code>{result.preset}</code>
              </div>

              {result.questions.map((q) => (
                <QuizCard key={q.number} q={q} />
              ))}

              {result.quiz_markdown && (
                <div className="output-section" style={{ marginTop: '1.5rem' }}>
                  <div className="output-header">
                    <span className="output-label">Quiz Markdown</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <div className="quiz-dir-toggle" style={{ margin: 0 }}>
                        <button
                          className={`quiz-dir-btn ${mdView === 'raw' ? 'active' : ''}`}
                          onClick={() => setMdView('raw')}
                        >Raw</button>
                        <button
                          className={`quiz-dir-btn ${mdView === 'rendered' ? 'active' : ''}`}
                          onClick={() => setMdView('rendered')}
                        >Rendered</button>
                      </div>
                      <CopyButton text={result.quiz_markdown} />
                    </div>
                  </div>

                  {mdView === 'raw' ? (
                    <textarea
                      className="code-output"
                      readOnly
                      value={result.quiz_markdown}
                      rows={Math.min(30, result.quiz_markdown.split('\n').length + 2)}
                      style={{ width: '100%', fontFamily: 'monospace', fontSize: '0.8rem', resize: 'vertical' }}
                    />
                  ) : (
                    <div className="quiz-preview-container">
                      <Preview content={toPreviewMd(result.quiz_markdown)} mode="markdown" />
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </>
      )}

      {activeDir === 'md-to-word' && <ToWordSection />}
    </div>
  );
}
