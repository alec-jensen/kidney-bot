import { useRef, useState } from "react";
import type { ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { DomainForm, type DomainFormHandle } from "../components/DomainForm";
import { AutoroleEditor } from "../components/AutoroleEditor";
import { HoneypotPanel } from "../components/HoneypotPanel";
import { ErrorBanner } from "../components/ErrorBanner";
import type { SettingsMap } from "../lib/api";

type StepKind = "intro" | "domain" | "done";
type StepStatus = "pending" | "configured" | "skipped";

interface WizardStep {
  key: string;
  title: string;
  kind: StepKind;
  domain?: string;
  /** 1-2 sentences of plain-language context: what the feature does, whether most servers need it. */
  context?: string;
  note?: string;
  extra?: (guildId: string, domainSettings: SettingsMap | null, setDomainSettings: (s: SettingsMap) => void) => ReactNode;
}

const STEPS: WizardStep[] = [
  {
    key: "welcome",
    title: "Welcome",
    kind: "intro",
  },
  {
    key: "guild_config",
    title: "General",
    kind: "domain",
    domain: "guild_config",
    context: "Core server behavior the bot needs to know about. Most servers should review this step.",
  },
  {
    key: "moderation",
    title: "Moderation",
    kind: "domain",
    domain: "moderation",
    context:
      "Escalation rules auto-suggest an action (like a mute or kick) after a member racks up repeat offenses.",
    note: "Built-in defaults are sensible for most servers — you can customize them later from the Moderation settings page.",
  },
  {
    key: "automod",
    title: "Automod",
    kind: "domain",
    domain: "automod",
    context: "Automatic filtering of spam, scam links, and other unwanted content. Recommended for most servers.",
  },
  {
    key: "autorole",
    title: "Auto role",
    kind: "domain",
    domain: "autorole",
    context: "Automatically gives new members one or more roles when they join, optionally after a delay.",
    extra: (guildId) => <AutoroleEditor guildId={guildId} />,
  },
  {
    key: "heuristics",
    title: "Heuristics",
    kind: "domain",
    domain: "heuristics",
    context:
      "The core anti-bot engine — scores new members on account age, avatar, username, and behavior, then alerts or acts automatically.",
    note: "Signal weights and thresholds are advanced tuning — find them under Heuristics settings later.",
  },
  {
    key: "honeypot",
    title: "Honeypot",
    kind: "domain",
    domain: "honeypot",
    context:
      "A decoy channel that looks tempting to bots but not real members — anyone who interacts with it gets caught automatically. Optional.",
    note: "Skip this if you don't want a bot-catching honeypot channel — nothing changes if you do.",
    extra: (guildId, domainSettings, setDomainSettings) => (
      <HoneypotPanel guildId={guildId} settings={domainSettings} onChanged={setDomainSettings} />
    ),
  },
  {
    key: "done",
    title: "Done",
    kind: "done",
  },
];

const DOMAIN_STEP_INDICES = STEPS.map((s, i) => (s.kind === "domain" ? i : -1)).filter((i) => i >= 0);

export function SetupWizard() {
  const { guildId } = useParams<{ guildId: string }>();
  const navigate = useNavigate();
  const [stepIndex, setStepIndex] = useState(0);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [domainSettings, setDomainSettings] = useState<SettingsMap | null>(null);
  const [statuses, setStatuses] = useState<Record<number, StepStatus>>(
    Object.fromEntries(DOMAIN_STEP_INDICES.map((i) => [i, "pending" as StepStatus])),
  );
  const formRef = useRef<DomainFormHandle>(null);

  if (!guildId) return null;

  const step = STEPS[stepIndex];
  const isFirst = stepIndex === 0;
  const isLast = stepIndex === STEPS.length - 1;

  function goNext() {
    setSaveError(null);
    setStepIndex((i) => Math.min(i + 1, STEPS.length - 1));
  }

  function goBack() {
    setSaveError(null);
    setStepIndex((i) => Math.max(i - 1, 0));
  }

  function handleSkip() {
    setStatuses((prev) => ({ ...prev, [stepIndex]: "skipped" }));
    goNext();
  }

  async function handleSaveAndContinue() {
    if (step.kind === "domain") {
      const ok = await formRef.current?.save();
      if (ok === false) {
        setSaveError("Couldn't save this step — check the fields above and try again.");
        return;
      }
      setStatuses((prev) => ({ ...prev, [stepIndex]: "configured" }));
    }
    goNext();
  }

  const configuredSteps = DOMAIN_STEP_INDICES.filter((i) => statuses[i] === "configured");
  const skippedSteps = DOMAIN_STEP_INDICES.filter((i) => statuses[i] !== "configured");

  return (
    <div className="setup-wizard">
      <Link className="back-link" to="/">
        &larr; Back to servers
      </Link>

      <div className="wizard-progress">
        Step {stepIndex + 1} of {STEPS.length}
        <div className="wizard-progress-bar">
          <div
            className="wizard-progress-bar-fill"
            style={{ width: `${((stepIndex + 1) / STEPS.length) * 100}%` }}
          />
        </div>
      </div>

      <h2>{step.title}</h2>

      {step.kind === "intro" && (
        <div className="wizard-step-body">
          <p>
            This wizard walks you through the essential settings for a new server: general behavior, moderation,
            automod, auto roles, the anti-bot heuristics engine, and the honeypot channel.
          </p>
          <p className="field-help">
            You can re-run any step later from the settings pages — nothing here is a one-time decision. "Skip"
            always means "don't change anything" — it never applies a default for you.
          </p>
        </div>
      )}

      {step.kind === "domain" && step.domain && (
        <div className="wizard-step-body">
          {step.context && <p className="wizard-step-context">{step.context}</p>}
          {step.note && <p className="notice">{step.note}</p>}
          <DomainForm
            guildId={guildId}
            domain={step.domain}
            hideActions
            key={step.domain}
            ref={formRef}
            onSettingsChange={setDomainSettings}
          >
            {step.extra?.(guildId, domainSettings, setDomainSettings)}
          </DomainForm>
          {saveError && <ErrorBanner message={saveError} />}
        </div>
      )}

      {step.kind === "done" && (
        <div className="wizard-step-body">
          <p>Setup complete. Your server is configured with the basics — you can fine-tune everything anytime.</p>
          <div className="wizard-summary">
            <div className="wizard-summary-column">
              <h4>Configured this run</h4>
              {configuredSteps.length === 0 ? (
                <p className="field-help">Nothing — every step was skipped.</p>
              ) : (
                <ul className="wizard-summary-list">
                  {configuredSteps.map((i) => (
                    <li key={STEPS[i].key}>{STEPS[i].title}</li>
                  ))}
                </ul>
              )}
            </div>
            <div className="wizard-summary-column">
              <h4>Skipped</h4>
              {skippedSteps.length === 0 ? (
                <p className="field-help">Nothing — every step was configured.</p>
              ) : (
                <ul className="wizard-summary-list wizard-summary-list--muted">
                  {skippedSteps.map((i) => (
                    <li key={STEPS[i].key}>{STEPS[i].title}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>
          <Link className="button" to={`/guilds/${guildId}/settings/guild_config`}>
            Go to full settings
          </Link>
        </div>
      )}

      <div className="wizard-actions">
        <button className="button button--link" disabled={isFirst} onClick={goBack}>
          Back
        </button>
        {!isLast && (
          <button className="button button--link" onClick={handleSkip}>
            Skip
          </button>
        )}
        {!isLast ? (
          <button className="button" onClick={() => void handleSaveAndContinue()}>
            {step.kind === "intro" ? "Get started" : "Save & continue"}
          </button>
        ) : (
          <button className="button" onClick={() => navigate("/")}>
            Finish
          </button>
        )}
      </div>
    </div>
  );
}
