import { useEffect, useState } from 'react';
import { healthCheck } from './api';
import ClipboardPanel from './components/ClipboardPanel';
import OcrPanel from './components/OcrPanel';
import ToWordPanel from './components/ToWordPanel';
import SettingsModal from './components/SettingsModal';
import './App.css';

type Tab = 'clipboard' | 'ocr' | 'word';

const TABS: { key: Tab; label: string }[] = [
  { key: 'clipboard', label: 'Clipboard → Text' },
  { key: 'ocr',       label: 'Image → OCR' },
  { key: 'word',      label: 'Text → Word' },
];

function App() {
  const [activeTab, setActiveTab] = useState<Tab>('clipboard');
  const [pandocOk, setPandocOk]   = useState<boolean | null>(null);
  const [darkMode, setDarkMode]   = useState(() =>
    window.matchMedia('(prefers-color-scheme: dark)').matches
  );
  const [settingsOpen, setSettingsOpen] = useState(false);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', darkMode ? 'dark' : 'light');
  }, [darkMode]);

  useEffect(() => {
    healthCheck().then((h) => setPandocOk(h.pandoc_installed)).catch(() => setPandocOk(false));
  }, []);

  return (
    <div className="app">
      <header>
        <h1>Word2LaTeX</h1>
        <div className="header-actions">
          <button className="theme-toggle" onClick={() => setSettingsOpen(true)} title="Settings">
            ⚙
          </button>
          <button className="theme-toggle" onClick={() => setDarkMode(!darkMode)} title="Toggle theme">
            {darkMode ? '☀' : '☽'}
          </button>
        </div>
      </header>

      <nav className="main-tab-nav">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`main-tab ${activeTab === t.key ? 'active' : ''}`}
            onClick={() => setActiveTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main>
        <div className={activeTab === 'clipboard' ? 'tab-panel active' : 'tab-panel'} hidden={activeTab !== 'clipboard'}>
          <ClipboardPanel pandocOk={pandocOk} />
        </div>
        <div className={activeTab === 'ocr' ? 'tab-panel active' : 'tab-panel'} hidden={activeTab !== 'ocr'}>
          <OcrPanel />
        </div>
        <div className={activeTab === 'word' ? 'tab-panel active' : 'tab-panel'} hidden={activeTab !== 'word'}>
          <ToWordPanel />
        </div>
      </main>

      <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}

export default App;
