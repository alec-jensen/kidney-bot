import { useState } from "react";
import { Link } from "react-router-dom";
import { DomainForm } from "../components/DomainForm";
import { WhitelistEditor } from "../components/WhitelistEditor";
import { AutoroleEditor } from "../components/AutoroleEditor";
import { EscalationRulesEditor } from "../components/EscalationRulesEditor";
import { HoneypotPanel } from "../components/HoneypotPanel";
import { NetworkSettings } from "../components/NetworkSettings";
import { HeuristicsOffNotice } from "../components/HeuristicsGate";
import { useHeuristicsEnabled } from "../lib/useHeuristicsEnabled";
import type { SettingsMap } from "../lib/api";

interface DomainPageProps {
  guildId: string;
  domain: string;
  resettable?: boolean;
}

export function DomainPage({ guildId, domain, resettable }: DomainPageProps) {
  const [honeypotSettings, setHoneypotSettings] = useState<SettingsMap | null>(null);
  // Bumped only by the enable/disable actions (not by the form's own load/save), so DomainForm
  // remounts and refetches the authoritative settings after a side-effecting honeypot action —
  // enableHoneypot()/disableHoneypot() write fields (mode, message_action, role ids) that the
  // panel's optimistic onChanged() patch doesn't fully know about.
  const [honeypotGeneration, setHoneypotGeneration] = useState(0);

  if (domain === "network") {
    return <NetworkSettings guildId={guildId} />;
  }

  if (domain === "honeypot") {
    const enabled = Boolean(honeypotSettings?.enabled);
    return (
      <DomainForm
        guildId={guildId}
        domain={domain}
        resettable={resettable}
        onSettingsChange={setHoneypotSettings}
        onDraftChange={setHoneypotSettings}
        hideFields={() => !enabled}
        beforeFields={() => (
          <HoneypotPanel
            guildId={guildId}
            settings={honeypotSettings}
            onChanged={(settings) => {
              setHoneypotSettings(settings);
              setHoneypotGeneration((g) => g + 1);
            }}
          />
        )}
        key={`${domain}-${honeypotGeneration}`}
      />
    );
  }

  if (domain === "heuristics") {
    return (
      <DomainForm
        guildId={guildId}
        domain={domain}
        resettable={resettable}
        hideFields={(draft) => !draft.enabled}
        alwaysVisibleFields={["enabled"]}
        beforeFields={(draft) =>
          !draft.enabled ? (
            <p className="field-help">
              The anti-bot heuristics engine scores new members on dozens of signals (account age, avatar, username
              patterns, join behavior, and more) and can automatically alert, kick, or ban accounts that look
              bot-like. Turn it on below to configure alert channels and action thresholds.
            </p>
          ) : null
        }
        key={domain}
      />
    );
  }

  if (domain === "heuristics_weights" || domain === "heuristics_thresholds") {
    return <HeuristicsSubPage guildId={guildId} domain={domain} resettable={resettable} />;
  }

  if (domain === "automod") {
    return (
      <DomainForm guildId={guildId} domain={domain} resettable={resettable} key={domain}>
        <WhitelistEditor guildId={guildId} />
      </DomainForm>
    );
  }

  if (domain === "autorole") {
    return (
      <DomainForm guildId={guildId} domain={domain} resettable={resettable} key={domain}>
        <AutoroleEditor guildId={guildId} />
      </DomainForm>
    );
  }

  if (domain === "moderation") {
    return (
      <DomainForm guildId={guildId} domain={domain} resettable={resettable} key={domain}>
        <EscalationRulesEditor guildId={guildId} />
      </DomainForm>
    );
  }

  return <DomainForm guildId={guildId} domain={domain} resettable={resettable} key={domain} />;
}

function HeuristicsSubPage({ guildId, domain, resettable }: DomainPageProps) {
  const { enabled, loaded } = useHeuristicsEnabled(guildId);
  return (
    <DomainForm
      guildId={guildId}
      domain={domain}
      resettable={resettable}
      beforeFields={() =>
        loaded && !enabled ? (
          <HeuristicsOffNotice>
            The heuristics engine is currently off — these values are saved but have no effect until you{" "}
            <Link to={`/guilds/${guildId}/settings/heuristics`}>turn it on from the Heuristics page</Link>.
          </HeuristicsOffNotice>
        ) : null
      }
      key={domain}
    />
  );
}
