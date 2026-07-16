import { useChannelPicker, useRolePicker } from "../lib/pickers";
import type { FieldDescriptor, SettingsValue } from "../lib/api";
import { SpecialFieldInput } from "./SpecialFieldInput";
import { isSpecialField } from "../lib/specialFields";

interface FieldInputProps {
  guildId: string;
  field: FieldDescriptor;
  value: SettingsValue;
  onChange: (value: SettingsValue) => void;
  disabled?: boolean;
}

export function FieldInput({ guildId, field, value, onChange, disabled }: FieldInputProps) {
  if (isSpecialField(field.name)) {
    return <SpecialFieldInput field={field} value={value} onChange={onChange} disabled={disabled} />;
  }

  if (field.type === "bool") {
    return (
      <input
        id={field.name}
        type="checkbox"
        checked={Boolean(value)}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
    );
  }

  if (field.type === "int" || field.type === "float") {
    return (
      <input
        id={field.name}
        type="number"
        min={field.min ?? undefined}
        max={field.max ?? undefined}
        step={field.type === "float" ? "any" : 1}
        disabled={disabled}
        value={value === null || value === undefined ? "" : String(value)}
        placeholder={field.default === null ? "unset" : String(field.default)}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
      />
    );
  }

  if (field.type === "enum") {
    return (
      <select
        id={field.name}
        disabled={disabled}
        value={value === null || value === undefined ? "" : String(value)}
        onChange={(e) => onChange(e.target.value)}
      >
        {(field.choices ?? []).map((choice) => (
          <option key={choice} value={choice}>
            {choice}
          </option>
        ))}
      </select>
    );
  }

  if (field.type === "channel") {
    return <ChannelInput guildId={guildId} field={field} value={value} onChange={onChange} disabled={disabled} />;
  }

  if (field.type === "role") {
    return <RoleInput guildId={guildId} field={field} value={value} onChange={onChange} disabled={disabled} />;
  }

  // "str"
  return (
    <input
      id={field.name}
      type="text"
      disabled={disabled}
      value={value === null || value === undefined ? "" : String(value)}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

function ChannelInput({ guildId, field, value, onChange, disabled }: FieldInputProps) {
  const { items, error } = useChannelPicker(guildId);

  if (error || items === null) {
    return (
      <div className="picker-fallback">
        <input
          id={field.name}
          type="text"
          disabled={disabled}
          placeholder="Channel ID"
          value={value === null || value === undefined ? "" : String(value)}
          onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}
        />
        {error ? (
          <p className="field-note">Couldn't load channels from Discord — paste a channel ID instead.</p>
        ) : (
          <p className="field-note">Loading channels…</p>
        )}
      </div>
    );
  }

  return (
    <select
      id={field.name}
      disabled={disabled}
      value={value === null || value === undefined ? "" : String(value)}
      onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}
    >
      <option value="">(not set)</option>
      {items.map((c) => (
        <option key={c.id} value={c.id}>
          # {c.name}
        </option>
      ))}
    </select>
  );
}

function RoleInput({ guildId, field, value, onChange, disabled }: FieldInputProps) {
  const { items, error } = useRolePicker(guildId);

  if (error || items === null) {
    return (
      <div className="picker-fallback">
        <input
          id={field.name}
          type="text"
          disabled={disabled}
          placeholder="Role ID"
          value={value === null || value === undefined ? "" : String(value)}
          onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}
        />
        {error ? (
          <p className="field-note">Couldn't load roles from Discord — paste a role ID instead.</p>
        ) : (
          <p className="field-note">Loading roles…</p>
        )}
      </div>
    );
  }

  return (
    <select
      id={field.name}
      disabled={disabled}
      value={value === null || value === undefined ? "" : String(value)}
      onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}
    >
      <option value="">(not set)</option>
      {items.map((r) => (
        <option key={r.id} value={r.id}>
          @ {r.name}
        </option>
      ))}
    </select>
  );
}
