interface SaveBarProps {
  saving: boolean;
  onSave: () => void;
  onDiscard: () => void;
  error?: string | null;
}

/** Sticky bottom bar shown while a form has unsaved changes. Replaces the inline save button. */
export function SaveBar({ saving, onSave, onDiscard, error }: SaveBarProps) {
  return (
    <div className="save-bar">
      <div className="save-bar-inner">
        <span className="save-bar-message">You have unsaved changes</span>
        {error && <span className="error save-bar-error">{error}</span>}
        <div className="save-bar-actions">
          <button className="button button--link" onClick={onDiscard} disabled={saving}>
            Discard
          </button>
          <button className="button" onClick={onSave} disabled={saving}>
            {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      </div>
    </div>
  );
}
