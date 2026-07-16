import type { FieldDescriptor, SettingsValue } from "../lib/api";

interface SpecialFieldInputProps {
  field: FieldDescriptor;
  value: SettingsValue;
  onChange: (value: SettingsValue) => void;
  disabled?: boolean;
}

const AUTO_DELETE_CHOICES: { label: string; value: number }[] = [
  { label: "Last hour", value: 3600 },
  { label: "6 hours", value: 21600 },
  { label: "24 hours", value: 86400 },
  { label: "3 days", value: 259200 },
  { label: "7 days", value: 604800 },
];

const THRESHOLD_ACTION_LABELS: Record<string, string> = {
  mute_threshold: "mute",
  kick_threshold: "kick",
  ban_threshold: "ban",
};

const DISABLED_THRESHOLD = 101;
const DEFAULT_ENABLED_SCORE = 85;

/** Renders a human-friendly control for known special-cased fields, or null if this field isn't special-cased. */
export function SpecialFieldInput({ field, value, onChange, disabled }: SpecialFieldInputProps) {
  if (field.name === "auto_delete_seconds") {
    return <AutoDeleteSecondsInput field={field} value={value} onChange={onChange} disabled={disabled} />;
  }

  if (field.name in THRESHOLD_ACTION_LABELS) {
    return <ThresholdInput field={field} value={value} onChange={onChange} disabled={disabled} />;
  }

  return null;
}

function AutoDeleteSecondsInput({ field, value, onChange, disabled }: SpecialFieldInputProps) {
  const current = typeof value === "number" ? value : Number(field.default ?? 86400);
  return (
    <select
      id={field.name}
      disabled={disabled}
      value={String(current)}
      onChange={(e) => onChange(Number(e.target.value))}
    >
      {AUTO_DELETE_CHOICES.map((choice) => (
        <option key={choice.value} value={choice.value}>
          {choice.label}
        </option>
      ))}
    </select>
  );
}

function ThresholdInput({ field, value, onChange, disabled }: SpecialFieldInputProps) {
  const action = THRESHOLD_ACTION_LABELS[field.name];
  const numeric = typeof value === "number" ? value : DISABLED_THRESHOLD;
  const isEnabled = numeric !== DISABLED_THRESHOLD;
  const score = isEnabled ? numeric : DEFAULT_ENABLED_SCORE;

  function handleToggle(checked: boolean) {
    onChange(checked ? DEFAULT_ENABLED_SCORE : DISABLED_THRESHOLD);
  }

  function handleScoreChange(raw: string) {
    if (raw === "") return;
    const n = Math.max(0, Math.min(100, Number(raw)));
    onChange(n);
  }

  return (
    <div className="threshold-field">
      <label className="checkbox-group-item threshold-field-toggle">
        <input
          type="checkbox"
          checked={isEnabled}
          disabled={disabled}
          onChange={(e) => handleToggle(e.target.checked)}
        />
        Enable auto-{action}
      </label>
      {isEnabled && (
        <div className="threshold-field-score">
          <input
            id={field.name}
            type="number"
            min={0}
            max={100}
            disabled={disabled}
            value={String(score)}
            onChange={(e) => handleScoreChange(e.target.value)}
          />
          <span className="field-note">score or higher triggers auto-{action}</span>
        </div>
      )}
    </div>
  );
}
