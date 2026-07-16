import { forwardRef, useEffect, useImperativeHandle, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api, ApiError, type FieldDescriptor, type SettingsMap, type SettingsValue } from "../lib/api";
import { FieldInput } from "./FieldInput";
import { Skeleton } from "./Skeleton";
import { SaveBar } from "./SaveBar";
import { ErrorBanner } from "./ErrorBanner";
import { useDirty } from "../lib/dirty";

interface DomainFormProps {
  guildId: string;
  domain: string;
  disabled?: boolean;
  disabledNotice?: string;
  /** Called once the settings map has loaded (and again after every successful save). */
  onSettingsChange?: (settings: SettingsMap) => void;
  /** Called on every draft change (including before save), so parent pages can react to live toggles. */
  onDraftChange?: (draft: SettingsMap) => void;
  /** Hides the built-in Save button/row — used by the setup wizard, which drives saving itself via the ref. */
  hideActions?: boolean;
  /** Shows a "Restore defaults" button next to Save that resets this domain's overrides. */
  resettable?: boolean;
  /**
   * When it returns true for the current draft, the generic field groups are gated down to just
   * `alwaysVisibleFields` (if any) — used for "feature is off" gates (e.g. heuristics.enabled,
   * honeypot.enabled) where the page wants to show only an explainer + enable control instead of
   * the full form. Note this must NOT hide every field needed to turn the feature back on.
   */
  hideFields?: (draft: SettingsMap) => boolean;
  /**
   * Field names that stay visible even when `hideFields` gates the rest of the form away — e.g.
   * the `enabled` checkbox itself, so the user always has a way to re-enable the feature.
   * Ignored when `hideFields` is not gating (all fields render as usual in that case).
   */
  alwaysVisibleFields?: string[];
  /** Renders above the field groups (or in place of them when hideFields is true), e.g. explainers/status cards. */
  beforeFields?: (draft: SettingsMap) => ReactNode;
  /** Renders below the field groups but above the Save button, e.g. for domain-specific notes. */
  children?: ReactNode;
}

export interface DomainFormHandle {
  /** Saves any dirty fields. No-op (resolves true) if nothing changed. Returns false on error. */
  save: () => Promise<boolean>;
}

function groupFields(fields: FieldDescriptor[]): { group: string | null; fields: FieldDescriptor[] }[] {
  const groups: { group: string | null; fields: FieldDescriptor[] }[] = [];
  const byGroup = new Map<string | null, FieldDescriptor[]>();
  for (const field of fields) {
    const key = field.group ?? null;
    let bucket = byGroup.get(key);
    if (!bucket) {
      bucket = [];
      byGroup.set(key, bucket);
      groups.push({ group: key, fields: bucket });
    }
    bucket.push(field);
  }
  // Ungrouped fields first.
  groups.sort((a, b) => {
    if (a.group === null) return -1;
    if (b.group === null) return 1;
    return 0;
  });
  return groups;
}

/** Whether `field`'s depends_on condition is satisfied by the current draft values. */
function isFieldVisible(field: FieldDescriptor, draft: SettingsMap): boolean {
  const dep = field.depends_on;
  if (!dep) return true;
  return draft[dep.field] === dep.value;
}

export const DomainForm = forwardRef<DomainFormHandle, DomainFormProps>(function DomainForm(
  {
    guildId,
    domain,
    disabled,
    disabledNotice,
    onSettingsChange,
    onDraftChange,
    hideActions,
    resettable,
    hideFields,
    alwaysVisibleFields,
    beforeFields,
    children,
  },
  ref,
) {
  const [fields, setFields] = useState<FieldDescriptor[] | null>(null);
  const [saved, setSaved] = useState<SettingsMap | null>(null);
  const [draft, setDraft] = useState<SettingsMap | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const { setDirty } = useDirty();

  useEffect(() => {
    setFields(null);
    setSaved(null);
    setDraft(null);
    setLoadError(null);
    setSaveError(null);
    setSavedMessage(null);
    Promise.all([api.schema(guildId, domain), api.getSettings(guildId, domain)])
      .then(([schema, settings]) => {
        setFields(schema);
        setSaved(settings);
        setDraft(settings);
        onSettingsChange?.(settings);
        onDraftChange?.(settings);
      })
      .catch((e: Error) => setLoadError(e instanceof ApiError ? e.message : e.message));
    // onSettingsChange/onDraftChange are intentionally excluded — callers may pass a fresh
    // function each render and we only want to refetch on guild/domain change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guildId, domain]);

  const groups = useMemo(() => (fields ? groupFields(fields) : []), [fields]);

  const dirty = useMemo(() => {
    if (!saved || !draft) return false;
    return Object.keys(draft).some((key) => draft[key] !== saved[key]);
  }, [saved, draft]);

  useEffect(() => {
    setDirty(dirty);
    // Clear global dirty flag on unmount so navigating away from an unsaved page
    // doesn't leave a stale prompt active for the next page.
    return () => setDirty(false);
  }, [dirty, setDirty]);

  async function handleSave(): Promise<boolean> {
    if (!draft || !saved) return true;
    const updates: SettingsMap = {};
    for (const key of Object.keys(draft)) {
      if (draft[key] !== saved[key]) updates[key] = draft[key];
    }
    if (Object.keys(updates).length === 0) return true;

    setSaving(true);
    setSaveError(null);
    try {
      const updated = await api.patchSettings(guildId, domain, updates);
      setSaved(updated);
      setDraft(updated);
      setSavedMessage("Saved.");
      onSettingsChange?.(updated);
      return true;
    } catch (e) {
      setSaveError(e instanceof ApiError ? e.message : (e as Error).message);
      return false;
    } finally {
      setSaving(false);
    }
  }

  function handleDiscard() {
    if (saved) {
      setDraft(saved);
      onDraftChange?.(saved);
    }
    setSaveError(null);
    setSavedMessage(null);
  }

  async function handleReset(): Promise<void> {
    const confirmed = window.confirm(
      "Restore all fields in this section to their default values? Your overrides will be removed.",
    );
    if (!confirmed) return;

    setResetting(true);
    setSaveError(null);
    try {
      const updated = await api.resetSettings(guildId, domain);
      setSaved(updated);
      setDraft(updated);
      setSavedMessage("Defaults restored.");
      onSettingsChange?.(updated);
      onDraftChange?.(updated);
    } catch (e) {
      setSaveError(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setResetting(false);
    }
  }

  useImperativeHandle(ref, () => ({ save: handleSave }));

  // Auto-fade the "Saved." confirmation after ~2.5s.
  useEffect(() => {
    if (!savedMessage) return;
    const timer = window.setTimeout(() => setSavedMessage(null), 2500);
    return () => window.clearTimeout(timer);
  }, [savedMessage]);

  if (loadError) return <ErrorBanner message={`Failed to load settings: ${loadError}`} />;
  if (!fields || !draft) return <Skeleton rows={5} />;

  function setValue(name: string, value: SettingsValue) {
    setDraft((prev) => {
      const next = prev ? { ...prev, [name]: value } : prev;
      if (next) onDraftChange?.(next);
      return next;
    });
    setSavedMessage(null);
  }

  const fieldsHidden = hideFields?.(draft) ?? false;

  return (
    <div className="domain-form">
      {disabled && disabledNotice && <p className="notice">{disabledNotice}</p>}
      {beforeFields?.(draft)}
      {groups.map((g) => {
        const visibleFields = g.fields.filter(
          (field) =>
            isFieldVisible(field, draft) && (!fieldsHidden || (alwaysVisibleFields?.includes(field.name) ?? false)),
        );
        if (visibleFields.length === 0) return null;
          return (
            <section className="field-group" key={g.group ?? "__ungrouped"}>
              {g.group && <h4>{g.group}</h4>}
              {visibleFields.map((field) => (
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
            </section>
          );
        })}

      {children}

      {!disabled && !hideActions && (
        <div className="form-actions">
          {resettable && (
            <button
              className="button button--danger"
              onClick={() => void handleReset()}
              disabled={resetting || saving}
            >
              {resetting ? "Restoring…" : "Restore defaults"}
            </button>
          )}
          {!dirty && savedMessage && <span className="saved-message">{savedMessage}</span>}
          {!dirty && saveError && <ErrorBanner message={saveError} />}
        </div>
      )}

      {!disabled && !hideActions && dirty && (
        <SaveBar saving={saving} onSave={() => void handleSave()} onDiscard={handleDiscard} error={saveError} />
      )}
    </div>
  );
});
