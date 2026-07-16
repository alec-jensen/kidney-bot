import { useEffect, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { api, type GuildSummary, type SettingsDomain } from "../lib/api";
import { guildIconUrl } from "../lib/discord";
import { buildNavSections, navLabel } from "../lib/navigation";
import { DomainPage } from "./DomainPage";
import { GuildSwitcher } from "../components/GuildSwitcher";
import { Skeleton } from "../components/Skeleton";
import { ErrorBanner } from "../components/ErrorBanner";
import { useDirty } from "../lib/dirty";

export function GuildSettings() {
  const { guildId, domainKey } = useParams<{ guildId: string; domainKey?: string }>();
  const [domains, setDomains] = useState<SettingsDomain[] | null>(null);
  const [guild, setGuild] = useState<GuildSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const { guardNavigation } = useDirty();

  useEffect(() => {
    if (!guildId) return;
    setDomains(null);
    setGuild(null);
    setError(null);
    api
      .domains(guildId)
      .then(setDomains)
      .catch((e: Error) => setError(e.message));
    api
      .guilds()
      .then((all) => setGuild(all.find((g) => g.id === guildId) ?? null))
      .catch(() => setGuild(null));
  }, [guildId]);

  if (!guildId) return null;
  if (error) return <ErrorBanner message={`Failed to load settings domains: ${error}`} />;
  if (!domains) return <Skeleton rows={6} />;

  if (!domainKey) {
    const first = domains[0];
    if (!first) return <p>No settings domains available.</p>;
    return <Navigate to={`/guilds/${guildId}/settings/${first.key}`} replace />;
  }

  const activeDomain = domains.find((d) => d.key === domainKey);
  const sections = buildNavSections(domains);
  const icon = guild ? guildIconUrl(guild) : null;

  function go(path: string) {
    guardNavigation(() => navigate(path));
  }

  return (
    <div className="guild-settings">
      <div className="guild-settings-header">
        <button className="back-link back-link--button" onClick={() => go("/")}>
          &larr; All servers
        </button>
        <div className="guild-settings-identity">
          {icon ? (
            <img className="guild-settings-icon" src={icon} alt="" />
          ) : (
            <div className="guild-settings-icon guild-settings-icon--placeholder">
              {(guild?.name ?? "?")[0]}
            </div>
          )}
          <span className="guild-settings-name">{guild?.name ?? "Loading…"}</span>
        </div>
        <GuildSwitcher currentGuildId={guildId} />
      </div>

      <div className="guild-settings-layout">
        <nav className="settings-nav">
          {sections.map((section) => (
            <div className="settings-nav-section" key={section.label}>
              <div className="settings-nav-heading">{section.label}</div>
              {section.items.map(({ domain, indent }) => (
                <button
                  key={domain.key}
                  type="button"
                  onClick={() => go(`/guilds/${guildId}/settings/${domain.key}`)}
                  className={
                    (domain.key === domainKey
                      ? "settings-nav-item settings-nav-item--active"
                      : "settings-nav-item") + (indent ? " settings-nav-item--indent" : "")
                  }
                >
                  {navLabel(domain)}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="settings-content">
          {activeDomain ? (
            <>
              <h2>{activeDomain.label}</h2>
              <p className="field-help settings-content-subtitle">{activeDomain.description}</p>
              <DomainPage guildId={guildId} domain={activeDomain.key} resettable={activeDomain.resettable} />
            </>
          ) : (
            <ErrorBanner message={`Unknown settings domain: ${domainKey}`} />
          )}
        </div>
      </div>
    </div>
  );
}
