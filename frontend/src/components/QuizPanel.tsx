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

// ── Markdown → Word: to-word panel ──────────────────────────────────────

function ToWordSection() {
  const [text, setText]         = useState('');
  const [status, setStatus]     = useState<string | null>(null);
  const [error, setError]       = useState<string | null>(null);
  const [loadingCb, setLoadingCb] = useState(false);
  const [loadingDx, setLoadingDx] = useState(false);

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
      await quizToDocx(text);
      setStatus('DOCX downloaded.');
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
        converts correctly; paragraph styles require a reference template.
      </p>

      <textarea
        className="code-output"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={'---\n\n## Problem stem with $math$\n\n### Option A\n### Option B\n\n<solution_title> Jawaban: A\n\nSolution body...\n\n---'}
        rows={12}
        style={{ width: '100%', fontFamily: 'monospace', fontSize: '0.8rem', resize: 'vertical', marginBottom: '0.75rem' }}
      />

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
          {loadingDx ? 'Generating…' : 'Download DOCX'}
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
