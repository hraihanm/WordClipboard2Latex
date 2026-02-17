export type TabKey = 'latex' | 'markdown' | 'html';

interface Props {
  activeTab: TabKey;
  onTabChange: (tab: TabKey) => void;
}

const TABS: { key: TabKey; label: string }[] = [
  { key: 'latex', label: 'LaTeX' },
  { key: 'markdown', label: 'Markdown' },
  { key: 'html', label: 'HTML' },
];

export default function OutputTabs({ activeTab, onTabChange }: Props) {
  return (
    <div className="tabs">
      {TABS.map((tab) => (
        <button
          key={tab.key}
          className={`tab ${activeTab === tab.key ? 'active' : ''}`}
          onClick={() => onTabChange(tab.key)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
