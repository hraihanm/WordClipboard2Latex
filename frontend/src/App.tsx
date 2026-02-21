import { useEffect, useState } from 'react';
import { type ConvertResult, type ClipboardInfo, convertClipboard, clipboardInfo, healthCheck } from './api';
import ConvertButton from './components/ConvertButton';
import OutputTabs, { type TabKey } from './components/OutputTabs';
import CodeOutput from './components/CodeOutput';
import CopyButton from './components/CopyButton';
import Preview from './components/Preview';
import './App.css';

function App() {
  const [result, setResult] = useState<ConvertResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>('markdown');
  const [darkMode, setDarkMode] = useState(() =>
    window.matchMedia('(prefers-color-scheme: dark)').matches
  );
  const [pandocOk, setPandocOk] = useState<boolean | null>(null);
  const [debugInfo, setDebugInfo] = useState<ClipboardInfo | null>(null);
  const [debugOpen, setDebugOpen] = useState(false);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', darkMode ? 'dark' : 'light');
  }, [darkMode]);

  useEffect(() => {
    healthCheck().then((h) => setPandocOk(h.pandoc_installed)).catch(() => setPandocOk(false));
  }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'v' && !loading && e.shiftKey) {
        e.preventDefault();
        handleConvert();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  });

  const handleConvert = async () => {
    setLoading(true);
    setError(null);
    try {
      const [data, debug] = await Promise.all([
        convertClipboard(),
        clipboardInfo(),
      ]);
      setResult(data);
      setDebugInfo(debug);
      if (data.warnings.length > 0) {
        setError(data.warnings.join('\n'));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Conversion failed');
    } finally {
      setLoading(false);
    }
  };

  const currentOutput = result ? result[activeTab] : '';

  const langMap: Record<TabKey, string> = {
    latex: 'latex',
    markdown: 'markdown',
    html: 'html',
  };

  return (
    <div className="app">
      <header>
        <h1>Word2LaTeX</h1>
        <div className="header-actions">
          {pandocOk === false && (
            <span className="warning-badge">Pandoc not found</span>
          )}
          <button
            className="theme-toggle"
            onClick={() => setDarkMode(!darkMode)}
            title="Toggle dark/light mode"
          >
            {darkMode ? '☀' : '☽'}
          </button>
        </div>
      </header>

      <main>
        <div className="convert-section">
          <p className="hint">
            Copy content from Microsoft Word, then click the button below.
          </p>
          <ConvertButton onClick={handleConvert} loading={loading} />
          <p className="shortcut-hint">Ctrl+Shift+V to convert</p>
        </div>

        {error && (
          <div className="error-box">
            {error}
          </div>
        )}

        {result && (
          <div className="output-section">
            <div className="output-header">
              <OutputTabs activeTab={activeTab} onTabChange={setActiveTab} />
              <CopyButton text={currentOutput} />
            </div>
            <CodeOutput content={currentOutput} language={langMap[activeTab]} />

            <div className="preview-section">
              <h3>Preview</h3>
              <Preview content={currentOutput} mode={activeTab} />
            </div>
          </div>
        )}

        {debugInfo && (
          <details className="debug-section" open={debugOpen} onToggle={(e) => setDebugOpen((e.target as HTMLDetailsElement).open)}>
            <summary>Clipboard Debug Info</summary>
            <div className="debug-content">
              <div className="debug-formats">
                <h4>Available Clipboard Formats</h4>
                <table className="debug-table">
                  <thead>
                    <tr><th>ID</th><th>Format</th></tr>
                  </thead>
                  <tbody>
                    {debugInfo.formats.map((f) => (
                      <tr key={f.id} className={f.name === 'HTML Format' ? 'highlight' : ''}>
                        <td>{f.id}</td>
                        <td>{f.name}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className={debugInfo.has_html ? 'status-ok' : 'status-warn'}>
                  {debugInfo.has_html ? 'HTML Format detected (OMML equations will be converted)' : 'No HTML Format — only plain text available'}
                </p>
              </div>

              <div className="debug-raw">
                <h4>Raw Clipboard HTML</h4>
                <pre className="debug-pre">{debugInfo.raw_html || '(empty)'}</pre>
              </div>

              {debugInfo.plain_text && (
                <div className="debug-raw">
                  <h4>Plain Text (for comparison)</h4>
                  <pre className="debug-pre">{debugInfo.plain_text}</pre>
                </div>
              )}
            </div>
          </details>
        )}
      </main>
    </div>
  );
}

export default App;
