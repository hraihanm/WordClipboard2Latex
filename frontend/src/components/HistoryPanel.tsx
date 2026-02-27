import { useCallback, useEffect, useState } from 'react';
import { getHistory, deleteHistoryItem, clearHistory, type HistoryItem } from '../api';

interface Props {
  tab: string;
  refreshKey: number;
  onRestore: (item: HistoryItem) => void;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1)   return 'just now';
  if (diffMin < 60)  return `${diffMin}m ago`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24)    return `${diffH}h ago`;
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export default function HistoryPanel({ tab, refreshKey, onRestore }: Props) {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [open, setOpen]   = useState(false);

  const load = useCallback(async () => {
    const data = await getHistory(tab);
    setItems(data);
  }, [tab]);

  useEffect(() => { load(); }, [load, refreshKey]);

  const handleDelete = async (id: number, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      await deleteHistoryItem(id);
      setItems((prev) => prev.filter((i) => i.id !== id));
    } catch {
      // Keep item in list if delete failed
    }
  };

  const handleClear = async () => {
    await clearHistory(tab);
    setItems([]);
  };

  return (
    <details
      className="history-panel"
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
    >
      <summary className="history-summary">
        <span className="history-summary-label">History</span>
        {items.length > 0 && <span className="history-count">{items.length}</span>}
        {items.length > 0 && open && (
          <button
            className="history-clear-btn"
            onClick={(e) => { e.preventDefault(); handleClear(); }}
          >
            Clear all
          </button>
        )}
      </summary>

      <div className="history-content">
        {items.length === 0 ? (
          <p className="history-empty">No history yet.</p>
        ) : (
          <div className="history-list">
            {items.map((item) => (
              <div key={item.id} className="history-card">
                <div
                  className="history-card-clickable"
                  onClick={() => onRestore(item)}
                  title="Click to restore"
                >
                  {item.thumbnail && (
                    <img src={item.thumbnail} className="history-thumb" alt="" />
                  )}
                  <div className="history-card-body">
                    <p className="history-title">{item.title}</p>
                    <p className="history-time">{formatTime(item.created_at)}</p>
                  </div>
                </div>
                <button
                  type="button"
                  className="history-delete-btn"
                  onClick={(e) => handleDelete(item.id, e)}
                  title="Remove"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </details>
  );
}
