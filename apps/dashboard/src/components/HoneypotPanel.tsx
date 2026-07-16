import { useState } from "react";
import { api, ApiError, type SettingsMap } from "../lib/api";
import { useChannelPicker } from "../lib/pickers";
import { ErrorBanner } from "./ErrorBanner";

interface HoneypotPanelProps {
  guildId: string;
  settings: SettingsMap | null;
  onChanged: (settings: SettingsMap) => void;
}

const MODE_LABELS: Record<string, string> = {
  visibility: "visibility",
  lockdown: "lockdown",
};

const ACTION_LABELS: Record<string, string> = {
  kick: "kick",
  ban: "ban",
  mute: "mute",
};

/**
 * Honeypot enable/disable action panel. When disabled, this is the ONLY thing shown on the
 * honeypot page (the generic config form is hidden behind it — see DomainPage). When enabled,
 * a compact status card with a Disable button is shown, and the generic form appears alongside it.
 */
export function HoneypotPanel({ guildId, settings, onChanged }: HoneypotPanelProps) {
  const { items: channels, error: channelsError } = useChannelPicker(guildId);
  const [channelId, setChannelId] = useState("");
  const [mode, setMode] = useState<"visibility" | "lockdown">("visibility");
  const [action, setAction] = useState<"kick" | "ban" | "mute">("kick");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const enabled = Boolean(settings?.enabled);

  async function enable() {
    if (!channelId) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await api.enableHoneypot(guildId, { channel_id: channelId, mode, action });
      setMessage("Honeypot enabled and verification message posted.");
      onChanged({ ...(settings ?? {}), enabled: true, mode, message_action: action });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function disable() {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await api.disableHoneypot(guildId);
      setMessage("Honeypot disabled.");
      onChanged({ ...(settings ?? {}), enabled: false });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (enabled) {
    const modeLabel = typeof settings?.mode === "string" ? (MODE_LABELS[settings.mode] ?? settings.mode) : "visibility";
    const actionLabel =
      typeof settings?.message_action === "string"
        ? (ACTION_LABELS[settings.message_action] ?? settings.message_action)
        : "kick";
    return (
      <section className="feature-status-card feature-status-card--active">
        <div className="feature-status-card-text">
          <strong>Honeypot active</strong>
          <span className="field-help">
            action: {actionLabel}, mode: {modeLabel}
          </span>
        </div>
        {error && <ErrorBanner message={error} />}
        {message && <span className="saved-message">{message}</span>}
        <button className="button button--danger" disabled={busy} onClick={() => void disable()}>
          {busy ? "Disabling…" : "Disable"}
        </button>
      </section>
    );
  }

  return (
    <section className="list-editor">
      <h3>Enable honeypot</h3>
      <p className="field-help">
        A honeypot is a decoy channel that looks tempting to bots but not to real members. Anyone who interacts with
        it gets caught automatically. Warning: enabling posts a verification message in the chosen channel
        immediately.
      </p>
      {error && <ErrorBanner message={error} />}
      {message && <p className="saved-message">{message}</p>}

      <div className="field-row">
        <div className="field">
          <label>Channel</label>
          {channels && !channelsError ? (
            <select value={channelId} onChange={(e) => setChannelId(e.target.value)}>
              <option value="">Select a channel…</option>
              {channels.map((c) => (
                <option key={c.id} value={c.id}>
                  # {c.name}
                </option>
              ))}
            </select>
          ) : (
            <div className="picker-fallback">
              <input
                type="text"
                placeholder="Channel ID"
                value={channelId}
                onChange={(e) => setChannelId(e.target.value)}
              />
              {channelsError && (
                <p className="field-note">Couldn't load channels from Discord — paste a channel ID instead.</p>
              )}
            </div>
          )}
        </div>
        <div className="field">
          <label>Mode</label>
          <select value={mode} onChange={(e) => setMode(e.target.value as "visibility" | "lockdown")}>
            <option value="visibility">Visibility</option>
            <option value="lockdown">Lockdown</option>
          </select>
        </div>
        <div className="field">
          <label>Action on message</label>
          <select value={action} onChange={(e) => setAction(e.target.value as "kick" | "ban" | "mute")}>
            <option value="kick">Kick</option>
            <option value="ban">Ban</option>
            <option value="mute">Mute</option>
          </select>
        </div>
      </div>

      <div className="form-actions">
        <button className="button" disabled={busy || !channelId} onClick={() => void enable()}>
          {busy ? "Enabling…" : "Enable honeypot"}
        </button>
      </div>
    </section>
  );
}
