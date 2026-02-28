import { useEffect, useState } from 'react';
import { getSettings, updateSettings, type AppSettings } from '../api';

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function SettingsModal({ open, onClose }: Props) {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [draft, setDraft] = useState<Partial<AppSettings>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (open) window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  useEffect(() => {
    if (open) {
      setError(null);
      getSettings()
        .then((s) => {
          setSettings(s);
          setDraft({ ollama_base_url: s.ollama_base_url, ollama_model: s.ollama_model });
        })
        .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load settings'));
    }
  }, [open]);

  const handleSave = async () => {
    const url = draft.ollama_base_url?.trim();
    const model = draft.ollama_model?.trim();
    if (!url || !model) {
      setError('Ollama URL and model are required');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await updateSettings({ ollama_base_url: url, ollama_model: model });
      setSettings((prev) => (prev ? { ...prev, ollama_base_url: url, ollama_model: model } : null));
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  if (!open) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Settings</h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        <div className="modal-body">
          <section className="settings-section">
            <h3>Ollama API</h3>
            <p className="settings-hint">
              Configure Ollama for local or remote vision OCR. Run <code>ollama pull llava</code> (or another vision model) first.
            </p>
            <div className="settings-field">
              <label htmlFor="ollama-url">Base URL</label>
              <input
                id="ollama-url"
                type="url"
                placeholder="http://localhost:11434"
                value={draft.ollama_base_url ?? settings?.ollama_base_url ?? ''}
                onChange={(e) => setDraft((d) => ({ ...d, ollama_base_url: e.target.value }))}
              />
            </div>
            <div className="settings-field">
              <label htmlFor="ollama-model">Model</label>
              <input
                id="ollama-model"
                type="text"
                placeholder="llava"
                value={draft.ollama_model ?? settings?.ollama_model ?? ''}
                onChange={(e) => setDraft((d) => ({ ...d, ollama_model: e.target.value }))}
              />
              <span className="settings-hint">e.g. llava, llava:13b, gemma3, moondream</span>
            </div>
          </section>
          {error && <div className="settings-error">{error}</div>}
        </div>
        <div className="modal-footer">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
