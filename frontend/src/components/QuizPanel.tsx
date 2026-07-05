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
## Sebuah planet mengorbit bintang bermassa $M_\\star = 1{,}2\\,M_\\odot$ dengan periode $P = 3{,}0$ tahun. Dengan hukum Kepler ketiga $P^2 = \\dfrac{4\\pi^2 a^3}{G M_\\star}$, setengah sumbu panjang orbitnya (dalam AU) paling mendekati …

- (A) $a \\approx 2{,}3\\ \\mathrm{AU}$
- (B) $a \\approx 2{,}0\\ \\mathrm{AU}$
- (C) $a \\approx 3{,}0\\ \\mathrm{AU}$
- (D) $a \\approx 1{,}6\\ \\mathrm{AU}$
- (E) $a \\approx 4{,}1\\ \\mathrm{AU}$

### Jawaban
A

### Pembahasan
Dalam satuan surya berlaku $P^2 = a^3 / M_\\star$ ($P$ dalam tahun, $a$ dalam AU, $M_\\star$ dalam $M_\\odot$), sehingga:

$$
\\begin{aligned}
a &= \\left( M_\\star\\,P^2 \\right)^{1/3} \\\\
  &= \\left( 1{,}2 \\times 3{,}0^2 \\right)^{1/3} \\\\
  &= \\left( 10{,}8 \\right)^{1/3} \\approx 2{,}21\\ \\mathrm{AU}
\\end{aligned}
$$

Nilai ini paling dekat dengan **2,3 AU**.

\`\`\`meta
type: mc
difficulty: 3
cognitive: Applying
quality: good
topics:
  - Mekanika Benda Langit/Hukum Kepler
  - Sistem Keplerian
source:
  kind: competition
  series: OSN
  stage: Provinsi
  year: 2023
\`\`\`

## Perhatikan klasifikasi spektral bintang. Manakah pernyataan yang **benar**? *(pilih semua yang sesuai)*

- (A) Bintang kelas O lebih panas daripada kelas B
- (B) Garis serapan hidrogen Balmer paling kuat pada kelas A
- (C) Bintang kelas M menampilkan pita molekul TiO
- (D) Urutan Harvard dari panas ke dingin adalah O–B–A–F–G–K–M
- (E) Matahari berkelas spektral B

### Jawaban
A, B, C, D

### Pembahasan
Ringkasan kelas spektral utama:

| Kelas | $T_\\mathrm{eff}$ (K) | Ciri khas |
|---|---|---|
| O | $> 30\\,000$ | garis He II |
| A | $\\sim 9\\,000$ | Balmer terkuat |
| G | $\\sim 5\\,800$ | logam netral (Matahari) |
| M | $< 3\\,900$ | pita molekul TiO |

Pernyataan **E salah**: Matahari berkelas \`G2V\`, bukan B. Sisanya benar.

---

Mnemonik klasik untuk mengingat urutan Harvard: *"Oh Be A Fine Girl/Guy, Kiss Me."*

## Kecepatan lepas dari permukaan Bumi ($M_\\oplus$, $R_\\oplus$) adalah $v_e = \\sqrt{2GM_\\oplus/R_\\oplus}$. Maka $v_e \\approx$ {{1}} km/s. Bila massa planet dilipatduakan pada jari-jari tetap, $v_e$ menjadi {{2}} kali semula. Proses lepas landas ini pada dasarnya melawan gaya {{3}}.

### Jawaban
1. [numerik:0.1] 11.2
2. [numerik:0.01] 1.41
3. [teks] gravitasi

### Pembahasan
Substitusi konstanta memberi:

$$
v_e = \\sqrt{\\frac{2GM_\\oplus}{R_\\oplus}} \\approx 1{,}12 \\times 10^4\\ \\mathrm{m/s} = 11{,}2\\ \\mathrm{km/s}
$$

Ketergantungan $v_e$ pada massa (jari-jari tetap):

$$
v_e \\propto \\sqrt{M}, \\qquad
\\begin{cases}
M \\to 2M &\\Rightarrow v_e \\to \\sqrt{2}\\,v_e \\approx 1{,}41\\,v_e \\\\
M \\to 4M &\\Rightarrow v_e \\to 2\\,v_e
\\end{cases}
$$

Poin penting:

- $v_e$ naik dengan faktor $\\sqrt{2}$ saat massa berlipat dua
- besaran ini tak bergantung pada massa roket
- yang harus dilawan sepenuhnya adalah tarikan **gravitasi** planet

## Diberikan matriks rotasi $R(\\theta) = \\begin{bmatrix} \\cos\\theta & -\\sin\\theta \\\\ \\sin\\theta & \\cos\\theta \\end{bmatrix}$. Nilai $\\det R(\\theta)$ dan $\\displaystyle \\lim_{\\theta \\to 0} \\frac{\\sin\\theta}{\\theta}$ berturut-turut adalah …

- (A) $1$ dan $1$
- (B) $\\cos 2\\theta$ dan $0$
- (C) $1$ dan $0$
- (D) $0$ dan $1$

### Jawaban
A

### Pembahasan
Determinannya memakai identitas Pythagoras:

$$
\\det R(\\theta) = \\cos^2\\theta - (-\\sin\\theta)(\\sin\\theta) = \\cos^2\\theta + \\sin^2\\theta = 1
$$

Limit fundamental (dari deret $\\sin\\theta = \\theta - \\tfrac{\\theta^3}{6} + \\cdots$):

$$
\\lim_{\\theta \\to 0} \\frac{\\sin\\theta}{\\theta} = 1
$$

Rotasi mempertahankan luas ($\\det = 1$) — sejalan dengan invariansi integral Gauss
$\\displaystyle \\int_{-\\infty}^{\\infty} e^{-x^2}\\,dx = \\sqrt{\\pi}$ terhadap rotasi sumbu, dan
dengan jumlahan energi mode $\\sum_{n=1}^{\\infty} \\frac{1}{n^2} = \\frac{\\pi^2}{6}$ yang tak bergantung basis.

## **Bacaan.** Sebuah satelit pada orbit rendah (LEO) mengalami hambatan atmosfer lemah, sehingga energi mekaniknya $E = -\\dfrac{GMm}{2a}$ berkurang perlahan. Berdasarkan bacaan itu, jawablah:

\\begin{enumerate}
\\item Jelaskan mengapa laju satelit justru **bertambah** saat orbitnya meluruh (paradoks satelit).
\\item Sebutkan besaran orbit yang berubah beserta arah perubahannya.
\\end{enumerate}

### Pembahasan
Karena $E = -\\dfrac{GMm}{2a}$, hilangnya energi (E makin negatif) memaksa $a$ mengecil. Laju orbit lingkaran $v = \\sqrt{GM/a}$ justru **naik** ketika $a$ turun — di situlah paradoksnya: gesekan memperlambat sesaat, tetapi konversi energi potensial ke kinetik lebih dominan.

Besaran yang berubah saat $a$ menyusut:

\\begin{itemize}
\\item setengah sumbu $a$: \\textbf{berkurang}
\\item laju orbit $v \\propto a^{-1/2}$: \\textbf{bertambah}
\\item periode $T \\propto a^{3/2}$: \\textbf{berkurang}
\\end{itemize}

> Intuisi: satelit "jatuh ke dalam sumur potensial", menukar ketinggian dengan kelajuan.

\`\`\`meta
type: essay
difficulty: 4
cognitive: Understanding
quality: good
topics:
  - Mekanika Benda Langit/Orbit
\`\`\`

## Turunkan hubungan antara magnitudo semu $m$, magnitudo mutlak $M$, dan jarak $d$ (dalam parsec), lalu jelaskan makna fisis modulus jarak $\\mu = m - M$. Sertakan bentuk matriks yang memetakan $(\\log_{10} d,\\,1)$ ke $\\mu$.

### Pembahasan
Fluks mengikuti hukum kuadrat terbalik, $F \\propto d^{-2}$. Dari definisi magnitudo:

$$
\\begin{aligned}
m - M &= -2{,}5 \\log_{10}\\!\\left(\\frac{F_d}{F_{10}}\\right) \\\\
      &= -2{,}5 \\log_{10}\\!\\left(\\frac{d}{10\\ \\mathrm{pc}}\\right)^{-2} \\\\
      &= 5 \\log_{10} d - 5
\\end{aligned}
$$

Sebagai transformasi afin terhadap $\\log_{10} d$, hubungan itu setara dengan perkalian matriks:

$$
\\mu =
\\begin{pmatrix} 5 & -5 \\end{pmatrix}
\\begin{pmatrix} \\log_{10} d \\\\ 1 \\end{pmatrix}
$$

> Modulus jarak $\\mu = m - M$ adalah "jarak dalam bahasa magnitudo": setiap kenaikan $\\mu$ sebesar $5$ berarti jarak menjadi $10\\times$ lebih jauh.

Karena $\\mu$ hanya bergantung pada $d$, mengukur $m$ dan mengetahui $M$ (mis. dari lilin standar seperti Cepheid) langsung memberi jarak.

\`\`\`meta
type: essay
difficulty: 4
cognitive: Analyzing
quality: needs_review
qualityIssues: [needs_diagram]
topics:
  - Fotometri/Magnitudo
\`\`\`
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
  const [includeMeta, setIncludeMeta] = useState(false);
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
      await quizToDocx(text, { includeSolutions, useTemplate, includeMeta, filename, templateFile });
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
        <label
          style={{
            display: 'flex', alignItems: 'center', gap: '0.3rem',
            cursor: includeSolutions ? 'pointer' : 'not-allowed', opacity: includeSolutions ? 1 : 0.5,
          }}
          title="Embed BANK_META as hidden text after each solution"
        >
          <input
            type="checkbox"
            checked={includeMeta}
            disabled={!includeSolutions}
            onChange={(e) => setIncludeMeta(e.target.checked)}
          />
          Metadata (hidden)
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
