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
---

## Sebuah bintang memiliki suhu permukaan $T = 6{,}000\\ \\mathrm{K}$ dan radius $R = 2{,}0\\ R_\\odot$. Luminositas bintang dinyatakan oleh hukum Stefan–Boltzmann:

$$
L = 4\\pi R^2 \\sigma T^4
$$

Jika luminositas Matahari $L_\\odot$ diperoleh saat $R = R_\\odot$ dan $T = T_\\odot$, maka luminositas bintang ini dalam satuan $L_\\odot$ adalah\\ldots

### $L \\approx 16\\ L_\\odot$
### $L \\approx 4\\ L_\\odot$
### $L \\approx 8\\ L_\\odot$
### $L \\approx 64\\ L_\\odot$

<solution_title> Jawaban: A

Karena $T = T_\\odot$, kontribusi suhu hilang, dan:

$$
\\frac{L}{L_\\odot} = \\left(\\frac{R}{R_\\odot}\\right)^2 = (2{,}0)^2 = \\boxed{4\\ L_\\odot}
$$

Jadi jawabannya **A**. \\textbf{Catatan:} kita menggunakan $T = T_\\odot$ agar faktor $T^4$ saling menghilangkan.

---

## Perhatikan persamaan kesetimbangan hidrostatik berikut:

\\begin{align}
\\frac{dP}{dr} &= -\\frac{G M(r) \\rho(r)}{r^2}
\\end{align}

Dari persamaan ini, \\emph{arah perubahan tekanan} terhadap jari-jari $r$ di dalam bintang adalah\\ldots

### Tekanan \\textbf{berkurang} ke arah luar, $dP/dr < 0$
### Tekanan bertambah ke arah luar, $dP/dr > 0$
### Tekanan konstan di seluruh interior, $dP/dr = 0$
### Tekanan bergantung pada komposisi kimia, bukan posisi

<solution_title> Jawaban: A

Karena $G$, $M(r)$, $\\rho(r)$, dan $r^2$ semuanya positif, tanda minus memastikan:

$$\\frac{dP}{dr} < 0$$

Tekanan \\textbf{berkurang} ke arah luar (atau \\emph{bertambah} ke arah pusat) — inilah yang menopang bintang melawan gravitasi.

---

## Tabel berikut menunjukkan sifat empat kelas bintang deret utama. Bintang manakah yang memiliki luminositas terbesar?

\\begin{tabular}{lccc}
\\hline
Kelas & $T_\\mathrm{eff}$ (K) & $R/R_\\odot$ & $L/L_\\odot$ \\\\
\\hline
O5 & $42{,}000$ & $12$ & $8 \\times 10^5$ \\\\
B0 & $30{,}000$ & $7$ & $5 \\times 10^4$ \\\\
A0 & $10{,}000$ & $2{,}4$ & $54$ \\\\
G2 (Matahari) & $5{,}778$ & $1{,}0$ & $1{,}0$ \\\\
\\hline
\\end{tabular}

### Bintang kelas O5
### Bintang kelas B0
### Bintang kelas A0
### Bintang kelas G2

<solution_title> Jawaban: A

Dari tabel, bintang kelas \\textbf{O5} memiliki $L/L_\\odot = 8 \\times 10^5$ — jauh melampaui kelas lainnya.

Ini konsisten dengan $L \\propto R^2 T^4$: bintang O5 \\emph{lebih besar dan lebih panas} secara bersamaan, sehingga luminositasnya meledak secara eksponensial.

---

## Hukum pergeseran Wien menyatakan $\\lambda_\\max T = b$ dengan $b = 2{,}898 \\times 10^6\\ \\mathrm{nm \\cdot K}$. Berapakah $\\lambda_\\max$ untuk Matahari ($T_\\odot = 5{,}778\\ \\mathrm{K}$)?

### $\\lambda_\\max \\approx 501\\ \\mathrm{nm}$ (hijau–kuning)
### $\\lambda_\\max \\approx 483\\ \\mathrm{nm}$ (biru–hijau)
### $\\lambda_\\max \\approx 620\\ \\mathrm{nm}$ (merah–oranye)
### $\\lambda_\\max \\approx 380\\ \\mathrm{nm}$ (ultraviolet)

<solution_title> Jawaban: A

$$
\\lambda_\\max = \\frac{2{,}898 \\times 10^6\\ \\mathrm{nm \\cdot K}}{5{,}778\\ \\mathrm{K}} \\approx \\boxed{501\\ \\mathrm{nm}}
$$

Panjang gelombang ini berada di spektrum \\emph{hijau–kuning} — bukan kebetulan bahwa mata manusia paling sensitif tepat di kisaran ini.

---

## Terdapat empat proses di dalam bintang deret utama:

\\begin{enumerate}[(a)]
  \\item Fusi hidrogen menjadi helium di inti ($T \\sim 10^7\\ \\mathrm{K}$)
  \\item Transfer energi dari inti ke selubung via konveksi atau radiasi
  \\item Pancaran foton dari fotosfer ke ruang angkasa
  \\item Reaksi fisi nuklir di selubung luar
\\end{enumerate}

Proses manakah yang \\textbf{tidak} terjadi pada bintang deret utama?

### (a) saja
### (b) dan (c)
### (d) saja
### (a), (b), dan (c)

<solution_title> Jawaban: C

Proses (a)–(c) adalah mekanisme inti bintang deret utama:

- \\textbf{Fusi hidrogen} menghasilkan energi di inti
- \\textbf{Konveksi/radiasi} mentransfer energi ke permukaan
- \\textbf{Emisi foton} melepas energi ke ruang angkasa

\\emph{Reaksi fisi} (d) \\textbf{tidak} terjadi di bintang deret utama — fisi adalah pemecahan inti berat (reaktor nuklir / senjata), bukan sumber energi bintang.
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
        placeholder={'---\n\n## Problem stem with $math$\n\n### Option A\n### Option B\n\n<solution_title> Jawaban: A\n\nSolution body...\n\n---'}
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
