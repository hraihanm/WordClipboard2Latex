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
          setDraft({
            ollama_base_url: s.ollama_base_url,
            ollama_model: s.ollama_model,
            lmstudio_base_url: s.lmstudio_base_url,
            lmstudio_model: s.lmstudio_model,
          });
        })
        .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load settings'));
    }
  }, [open]);

  const handleSave = async () => {
    const ollamaUrl   = draft.ollama_base_url?.trim();
    const ollamaModel = draft.ollama_model?.trim();
    const lmsUrl      = draft.lmstudio_base_url?.trim();
    const lmsModel    = draft.lmstudio_model?.trim();
    if (!ollamaUrl || !ollamaModel) {
      setError('Ollama URL and model are required');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await updateSettings({
        ollama_base_url:   ollamaUrl,
        ollama_model:      ollamaModel,
        lmstudio_base_url: lmsUrl   || 'http://localhost:1234/v1',
        lmstudio_model:    lmsModel || 'local-model',
      });
      setSettings((prev) =>
        prev
          ? { ...prev, ollama_base_url: ollamaUrl, ollama_model: ollamaModel,
              lmstudio_base_url: lmsUrl || prev.lmstudio_base_url,
              lmstudio_model:    lmsModel || prev.lmstudio_model }
          : null,
      );
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

          <section className="settings-section" style={{ marginTop: '1.25rem' }}>
            <h3>LM Studio API</h3>
            <p className="settings-hint">
              OpenAI-compatible local API. Load a vision model in LM Studio and start the server.
            </p>
            <div className="settings-field">
              <label htmlFor="lms-url">Base URL</label>
              <input
                id="lms-url"
                type="url"
                placeholder="http://localhost:1234/v1"
                value={draft.lmstudio_base_url ?? settings?.lmstudio_base_url ?? ''}
                onChange={(e) => setDraft((d) => ({ ...d, lmstudio_base_url: e.target.value }))}
              />
            </div>
            <div className="settings-field">
              <label htmlFor="lms-model">Model ID</label>
              <input
                id="lms-model"
                type="text"
                placeholder="local-model"
                value={draft.lmstudio_model ?? settings?.lmstudio_model ?? ''}
                onChange={(e) => setDraft((d) => ({ ...d, lmstudio_model: e.target.value }))}
              />
              <span className="settings-hint">Copy the model identifier shown in LM Studio.</span>
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
