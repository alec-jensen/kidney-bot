import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import { Skeleton } from "./Skeleton";
import { ErrorBanner } from "./ErrorBanner";

export function WatchlistEditor({ guildId }: { guildId: string }) {
  const [items, setItems] = useState<Awaited<ReturnType<typeof api.networkWatchlist>> | null>(null);
  const [userId, setUserId] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .networkWatchlist(guildId)
      .then(setItems)
      .catch((e: Error) => setError(e.message));
  }, [guildId]);

  async function add() {
    const id = userId.trim();
    if (!id) return;
    setBusy(true);
    setError(null);
    try {
      setItems(await api.addNetworkWatchlistItem(guildId, id, reason.trim()));
      setUserId("");
      setReason("");
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
      setItems(await api.removeNetworkWatchlistItem(guildId, id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="list-editor">
      <h3>Watchlist</h3>
      <p className="field-help">Users flagged network-wide for extra scrutiny.</p>
      {error && <ErrorBanner message={error} />}
      {items === null ? (
        <Skeleton rows={2} />
      ) : items.length === 0 ? (
        <p className="list-empty">Nothing on the watchlist yet — add a user ID and reason below.</p>
      ) : (
        <ul className="list-editor-rows">
          {items.map((item) => (
            <li key={item.user_id} className="list-editor-row">
              <span>
                {item.user_id}
                {item.reason && <span className="list-editor-detail"> — {item.reason}</span>}
              </span>
              <button className="button button--danger" disabled={busy} onClick={() => void remove(item.user_id)}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="list-editor-add">
        <input type="text" placeholder="User ID" value={userId} onChange={(e) => setUserId(e.target.value)} />
        <input type="text" placeholder="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
        <button className="button" disabled={busy || !userId.trim()} onClick={() => void add()}>
          Add
        </button>
      </div>
    </section>
  );
}
