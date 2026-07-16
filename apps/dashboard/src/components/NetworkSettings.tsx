import { useEffect, useMemo, useState } from "react";
import { api, ApiError, type FieldDescriptor, type NetworkResponse, type SettingsMap, type SettingsValue } from "../lib/api";
import { FieldInput } from "./FieldInput";
import { WatchlistEditor } from "./WatchlistEditor";
import { Skeleton } from "./Skeleton";
import { SaveBar } from "./SaveBar";
import { ErrorBanner } from "./ErrorBanner";
import { useDirty } from "../lib/dirty";

function isFieldVisible(field: FieldDescriptor, draft: SettingsMap): boolean {
  const dep = field.depends_on;
  if (!dep) return true;
  return draft[dep.field] === dep.value;
}

export function NetworkSettings({ guildId }: { guildId: string }) {
  const [info, setInfo] = useState<NetworkResponse | null>(null);
  const [fields, setFields] = useState<FieldDescriptor[] | null>(null);
  const [draft, setDraft] = useState<SettingsMap | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const { setDirty } = useDirty();

  useEffect(() => {
    setInfo(null);
    setFields(null);
    setDraft(null);
    setLoadError(null);
    Promise.all([api.network(guildId), api.networkSchema(guildId)])
      .then(([networkInfo, schema]) => {
        setInfo(networkInfo);
        setFields(schema);
        setDraft(networkInfo.settings ?? {});
      })
      .catch((e: Error) => setLoadError(e.message));
  }, [guildId]);

  const dirty = useMemo(() => {
    if (!info?.settings || !draft) return false;
    return Object.keys(draft).some((key) => draft[key] !== info.settings![key]);
  }, [info, draft]);

  useEffect(() => {
    setDirty(dirty);
    return () => setDirty(false);
  }, [dirty, setDirty]);

  // Auto-fade the "Saved." confirmation after ~2.5s.
  useEffect(() => {
    if (!savedMessage) return;
    const timer = window.setTimeout(() => setSavedMessage(null), 2500);
    return () => window.clearTimeout(timer);
  }, [savedMessage]);

  if (loadError) return <ErrorBanner message={`Failed to load network settings: ${loadError}`} />;
  if (!info) return <Skeleton rows={3} />;

  if (!info.member) {
    return (
      <p className="notice">
        This server isn't part of a network — create or join one with <code>/network create</code> or{" "}
        <code>/network join</code> in Discord.
      </p>
    );
  }

  if (!fields || !draft) return <Skeleton rows={5} />;

  function setValue(name: string, value: SettingsValue) {
    setDraft((prev) => (prev ? { ...prev, [name]: value } : prev));
    setSavedMessage(null);
  }

  function handleDiscard() {
    if (info?.settings) setDraft(info.settings);
    setSaveError(null);
    setSavedMessage(null);
  }

  async function handleSave() {
    if (!draft || !info?.settings) return;
    const updates: SettingsMap = {};
    for (const key of Object.keys(draft)) {
      if (draft[key] !== info.settings[key]) updates[key] = draft[key];
    }
    if (Object.keys(updates).length === 0) return;
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await api.patchNetwork(guildId, updates);
      setInfo((prev) => (prev ? { ...prev, settings: updated } : prev));
      setDraft(updated);
      setSavedMessage("Saved.");
    } catch (e) {
      setSaveError(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const disabled = !info.is_owner;

  return (
    <div className="domain-form">
      <div className="network-summary">
        <h3>{info.network?.name}</h3>
        <p className="field-help">{info.network?.guild_count} server(s) in this network.</p>
      </div>

      {disabled && (
        <p className="notice">Only the network owner can change these settings. Showing current values, read-only.</p>
      )}

      {fields.filter((field) => isFieldVisible(field, draft)).map((field) => (
        <div className="field" key={field.name}>
          <label htmlFor={field.name}>{field.label}</label>
          <FieldInput
            guildId={guildId}
            field={field}
            value={draft[field.name]}
            onChange={(v) => setValue(field.name, v)}
            disabled={disabled}
          />
          <p className="field-help">{field.help}</p>
        </div>
      ))}

      {!disabled && !dirty && (savedMessage || saveError) && (
        <div className="form-actions">
          {savedMessage && <span className="saved-message">{savedMessage}</span>}
          {saveError && <ErrorBanner message={saveError} />}
        </div>
      )}

      {!disabled && dirty && (
        <SaveBar saving={saving} onSave={() => void handleSave()} onDiscard={handleDiscard} error={saveError} />
      )}

      <WatchlistEditor guildId={guildId} />
    </div>
  );
}
