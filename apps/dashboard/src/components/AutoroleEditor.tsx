import { useEffect, useState } from "react";
import { api, ApiError, type AutoRoleEntry } from "../lib/api";
import { useRolePicker } from "../lib/pickers";
import { Skeleton } from "./Skeleton";
import { ErrorBanner } from "./ErrorBanner";

export function AutoroleEditor({ guildId }: { guildId: string }) {
  const [items, setItems] = useState<AutoRoleEntry[] | null>(null);
  const [roleId, setRoleId] = useState("");
  const [delay, setDelay] = useState("0");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { items: roles, error: rolesError } = useRolePicker(guildId);

  useEffect(() => {
    api
      .autoroleRoles(guildId)
      .then(setItems)
      .catch((e: Error) => setError(e.message));
  }, [guildId]);

  function roleName(id: string): string {
    return roles?.find((r) => r.id === id)?.name ?? id;
  }

  async function upsert() {
    const id = roleId.trim();
    if (!id) return;
    setBusy(true);
    setError(null);
    try {
      setItems(await api.upsertAutoroleRole(guildId, id, Number(delay) || 0));
      setRoleId("");
      setDelay("0");
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
      setItems(await api.removeAutoroleRole(guildId, id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="list-editor">
      <h3>Auto-assigned roles</h3>
      <p className="field-help">Roles given to new members, optionally after a delay (in seconds).</p>
      {error && <ErrorBanner message={error} />}
      {items === null ? (
        <Skeleton rows={2} />
      ) : items.length === 0 ? (
        <p className="list-empty">No auto roles yet — pick a role and add it below.</p>
      ) : (
        <ul className="list-editor-rows">
          {items.map((item) => (
            <li key={item.id} className="list-editor-row">
              <span>
                @ {roleName(item.id)}
                {item.delay > 0 && <span className="list-editor-detail"> — {item.delay}s delay</span>}
              </span>
              <button className="button button--danger" disabled={busy} onClick={() => void remove(item.id)}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="list-editor-add">
        {roles && !rolesError ? (
          <select value={roleId} onChange={(e) => setRoleId(e.target.value)}>
            <option value="">Select a role…</option>
            {roles.map((r) => (
              <option key={r.id} value={r.id}>
                @ {r.name}
              </option>
            ))}
          </select>
        ) : (
          <div className="picker-fallback">
            <input type="text" placeholder="Role ID" value={roleId} onChange={(e) => setRoleId(e.target.value)} />
            <p className="field-note">Couldn't load roles from Discord — paste a role ID instead.</p>
          </div>
        )}
        <input
          type="number"
          min={0}
          placeholder="Delay (seconds)"
          value={delay}
          onChange={(e) => setDelay(e.target.value)}
        />
        <button className="button" disabled={busy || !roleId.trim()} onClick={() => void upsert()}>
          Add / update
        </button>
      </div>
    </section>
  );
}
