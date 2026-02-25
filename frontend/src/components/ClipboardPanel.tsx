import { useEffect, useState } from 'react';
import { type ConvertResult, type ClipboardInfo, convertClipboard, clipboardInfo, addHistory, type HistoryItem } from '../api';
import ConvertButton from './ConvertButton';
import OutputTabs, { type TabKey } from './OutputTabs';
import CodeOutput from './CodeOutput';
import CopyButton from './CopyButton';
import Preview from './Preview';
import HistoryPanel from './HistoryPanel';

function makeTitle(text: string): string {
  return text.replace(/^#+\s*/gm, '').replace(/\*\*|__|_|\*/g, '').trim().split('\n')[0].slice(0, 70) || 'Untitled';
}

interface Props {
  pandocOk: boolean | null;
}

export default function ClipboardPanel({ pandocOk }: Props) {
  const [result, setResult]       = useState<ConvertResult | null>(null);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState<string | null>(null);
  const [codeTab, setCodeTab]     = useState<TabKey>('markdown');
  const [previewTab, setPreviewTab] = useState<TabKey>('markdown');
  const [debugInfo, setDebugInfo] = useState<ClipboardInfo | null>(null);
  const [debugOpen, setDebugOpen] = useState(false);
  const [historyKey, setHistoryKey] = useState(0);

  const handleConvert = async () => {
    setLoading(true);
    setError(null);
    try {
      const [data, debug] = await Promise.all([convertClipboard(), clipboardInfo()]);
      setResult(data);
      setDebugInfo(debug);
      if (data.warnings.length > 0) setError(data.warnings.join('\n'));
      await addHistory('clipboard', makeTitle(data.markdown || data.latex), {
        markdown: data.markdown, latex: data.latex, html: data.html,
      });
      setHistoryKey((k) => k + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Conversion failed');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'v') {
        e.preventDefault();
        if (!loading) handleConvert();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  });

  const handleRestore = (item: HistoryItem) => {
    const d = item.data as { markdown: string; latex: string; html: string };
    setResult({ markdown: d.markdown, latex: d.latex, html: d.html, warnings: [] });
    setError(null);
  };

  const langMap: Record<TabKey, string> = { latex: 'latex', markdown: 'markdown', html: 'html' };

  return (
    <div className="clipboard-panel">
      {pandocOk === false && (
        <div className="error-box" style={{ marginBottom: '1rem' }}>
          Pandoc not found — equation conversion will be limited.
        </div>
      )}

      <div className="convert-section">
        <p className="hint">Copy content from Microsoft Word, then click the button below.</p>
        <ConvertButton onClick={handleConvert} loading={loading} />
        <p className="shortcut-hint">Ctrl+Shift+V to convert</p>
      </div>

      {error && <div className="error-box">{error}</div>}

      {result && (
        <div className="output-grid">
          <div className="output-panel">
            <div className="panel-header">
              <div className="panel-title-tabs">
                <span className="panel-label">Code</span>
                <OutputTabs activeTab={codeTab} onTabChange={setCodeTab} />
              </div>
              <CopyButton text={result[codeTab]} />
            </div>
            <CodeOutput content={result[codeTab]} language={langMap[codeTab]} />
          </div>

          <div className="output-panel">
            <div className="panel-header">
              <div className="panel-title-tabs">
                <span className="panel-label">Preview</span>
                <OutputTabs activeTab={previewTab} onTabChange={setPreviewTab} />
              </div>
            </div>
            <div className="preview-wrapper">
              <Preview content={result[previewTab]} mode={previewTab} />
            </div>
          </div>
        </div>
      )}

      <HistoryPanel tab="clipboard" refreshKey={historyKey} onRestore={handleRestore} />

      {debugInfo && (
        <details
          className="debug-section"
          open={debugOpen}
          onToggle={(e) => setDebugOpen((e.target as HTMLDetailsElement).open)}
          style={{ marginTop: '1.5rem' }}
        >
          <summary>Clipboard Debug Info</summary>
          <div className="debug-content">
            <div className="debug-formats">
              <h4>Available Clipboard Formats</h4>
              <table className="debug-table">
                <thead><tr><th>ID</th><th>Format</th></tr></thead>
                <tbody>
                  {debugInfo.formats.map((f) => (
                    <tr key={f.id} className={f.name === 'HTML Format' ? 'highlight' : ''}>
                      <td>{f.id}</td><td>{f.name}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className={debugInfo.has_html ? 'status-ok' : 'status-warn'}>
                {debugInfo.has_html
                  ? 'HTML Format detected (OMML equations will be converted)'
                  : 'No HTML Format — only plain text available'}
              </p>
            </div>
            <div className="debug-raw">
              <h4>Raw Clipboard HTML</h4>
              <pre className="debug-pre">{debugInfo.raw_html || '(empty)'}</pre>
            </div>
            {debugInfo.plain_text && (
              <div className="debug-raw">
                <h4>Plain Text</h4>
                <pre className="debug-pre">{debugInfo.plain_text}</pre>
              </div>
            )}
          </div>
        </details>
      )}
    </div>
  );
}
