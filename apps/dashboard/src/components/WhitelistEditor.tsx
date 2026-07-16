import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import { Skeleton } from "./Skeleton";
import { ErrorBanner } from "./ErrorBanner";

export function WhitelistEditor({ guildId }: { guildId: string }) {
  const [items, setItems] = useState<string[] | null>(null);
  const [newId, setNewId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .automodWhitelist(guildId)
      .then(setItems)
      .catch((e: Error) => setError(e.message));
  }, [guildId]);

  async function add() {
    const id = newId.trim();
    if (!id) return;
    setBusy(true);
    setError(null);
    try {
      setItems(await api.addAutomodWhitelistItem(guildId, id));
      setNewId("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setBusy(true);
    setError(null);
    try {
      setItems(await api.removeAutomodWhitelistItem(guildId, id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="list-editor">
      <h3>Whitelist</h3>
      <p className="field-help">User or channel IDs exempt from automod filtering.</p>
      {error && <ErrorBanner message={error} />}
      {items === null ? (
        <Skeleton rows={2} />
      ) : items.length === 0 ? (
        <p className="list-empty">Nothing whitelisted yet — add a user or channel ID below.</p>
      ) : (
        <ul className="list-editor-rows">
          {items.map((id) => (
            <li key={id} className="list-editor-row">
              <span>{id}</span>
              <button className="button button--danger" disabled={busy} onClick={() => void remove(id)}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="list-editor-add">
        <input
          type="text"
          placeholder="User or channel ID"
          value={newId}
          onChange={(e) => setNewId(e.target.value)}
        />
        <button className="button" disabled={busy || !newId.trim()} onClick={() => void add()}>
          Add
        </button>
      </div>
    </section>
  );
}
