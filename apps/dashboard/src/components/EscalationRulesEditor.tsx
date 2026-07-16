import { useEffect, useState } from "react";
import { api, ApiError, type EscalationRulesResponse, type EscalationSuggestion } from "../lib/api";
import { Skeleton } from "./Skeleton";
import { ErrorBanner } from "./ErrorBanner";

const CONDITION_ACTION_TYPES = ["warn", "mute", "tempmute", "kick", "ban", "unmute", "unban"];
const SUGGESTION_ACTION_TYPES = ["warn", "tempmute", "mute", "kick", "ban"];

interface DraftSuggestion {
  action_type: string;
  duration: string;
}

function summarize(actionTypes: string[], minCount: number, windowDays: number, suggestions: EscalationSuggestion[]) {
  const conditions = actionTypes.join(", ");
  const suggestionText = suggestions
    .map((s) => (s.duration ? `${s.action_type} (${s.duration})` : s.action_type))
    .join(", ");
  return `After ${minCount} ${conditions} in ${windowDays} day${windowDays === 1 ? "" : "s"} → suggest ${suggestionText || "nothing"}`;
}

export function EscalationRulesEditor({ guildId }: { guildId: string }) {
  const [data, setData] = useState<EscalationRulesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [conditionTypes, setConditionTypes] = useState<string[]>([]);
  const [minCount, setMinCount] = useState("3");
  const [windowDays, setWindowDays] = useState("7");
  const [suggestions, setSuggestions] = useState<DraftSuggestion[]>([{ action_type: "warn", duration: "" }]);

  useEffect(() => {
    api
      .escalationRules(guildId)
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, [guildId]);

  function toggleConditionType(type: string) {
    setConditionTypes((prev) => (prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]));
  }

  function updateSuggestion(index: number, patch: Partial<DraftSuggestion>) {
    setSuggestions((prev) => prev.map((s, i) => (i === index ? { ...s, ...patch } : s)));
  }

  function addSuggestion() {
    setSuggestions((prev) => [...prev, { action_type: "warn", duration: "" }]);
  }

  function removeSuggestion(index: number) {
    setSuggestions((prev) => prev.filter((_, i) => i !== index));
  }

  async function addRule() {
    if (conditionTypes.length === 0 || suggestions.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.addEscalationRule(guildId, {
        action_types: conditionTypes,
        min_count: Number(minCount) || 1,
        window_days: Number(windowDays) || 1,
        suggestions: suggestions
          .filter((s) => s.action_type)
          .map((s) => (s.duration.trim() ? { action_type: s.action_type, duration: s.duration.trim() } : { action_type: s.action_type })),
      });
      setData(result);
      setConditionTypes([]);
      setMinCount("3");
      setWindowDays("7");
      setSuggestions([{ action_type: "warn", duration: "" }]);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function removeRule(ruleId: string) {
    setBusy(true);
    setError(null);
    try {
      setData(await api.removeEscalationRule(guildId, ruleId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function resetRules() {
    setBusy(true);
    setError(null);
    try {
      setData(await api.resetEscalationRules(guildId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="list-editor">
      <h3>Escalation rules</h3>
      <p className="field-help">
        When a member accumulates enough matching mod actions in the window, the bot suggests further action.
      </p>
      {error && <ErrorBanner message={error} />}
      {data === null ? (
        <Skeleton rows={2} />
      ) : (
        <>
          {data.using_defaults && <p className="notice">Using built-in default rules.</p>}
          {data.rules.length === 0 ? (
            <p className="list-empty">No custom escalation rules yet — add one below, or rely on the defaults.</p>
          ) : (
            <ul className="list-editor-rows">
              {data.rules.map((rule) => (
                <li key={rule.id} className="list-editor-row list-editor-row--card">
                  <span>
                    {summarize(rule.conditions.action_types, rule.conditions.min_count, rule.conditions.window_days, rule.suggestions)}
                  </span>
                  <button className="button button--danger" disabled={busy} onClick={() => void removeRule(rule.id)}>
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="list-editor-add-block">
            <button className="button" disabled={busy} onClick={() => void resetRules()}>
              Reset to defaults
            </button>
          </div>
        </>
      )}

      <div className="escalation-add-form">
        <h4>Add rule</h4>
        <div className="field">
          <label>Condition action types</label>
          <div className="checkbox-group">
            {CONDITION_ACTION_TYPES.map((type) => (
              <label key={type} className="checkbox-group-item">
                <input
                  type="checkbox"
                  checked={conditionTypes.includes(type)}
                  onChange={() => toggleConditionType(type)}
                />
                {type}
              </label>
            ))}
          </div>
        </div>
        <div className="field-row">
          <div className="field">
            <label>Minimum count</label>
            <input type="number" min={1} value={minCount} onChange={(e) => setMinCount(e.target.value)} />
          </div>
          <div className="field">
            <label>Window (days)</label>
            <input type="number" min={1} value={windowDays} onChange={(e) => setWindowDays(e.target.value)} />
          </div>
        </div>
        <div className="field">
          <label>Suggestions</label>
          {suggestions.map((s, i) => (
            <div className="field-row" key={i}>
              <select value={s.action_type} onChange={(e) => updateSuggestion(i, { action_type: e.target.value })}>
                {SUGGESTION_ACTION_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
              <input
                type="text"
                placeholder="Duration (e.g. 4h, tempmute only)"
                value={s.duration}
                onChange={(e) => updateSuggestion(i, { duration: e.target.value })}
              />
              <button
                className="button button--danger"
                disabled={suggestions.length <= 1}
                onClick={() => removeSuggestion(i)}
              >
                Remove
              </button>
            </div>
          ))}
          <button className="button button--link" onClick={addSuggestion}>
            + Add suggestion
          </button>
        </div>
        <button className="button" disabled={busy || conditionTypes.length === 0} onClick={() => void addRule()}>
          Add rule
        </button>
      </div>
    </section>
  );
}
