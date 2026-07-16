import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type GuildSummary } from "../lib/api";
import { guildIconUrl } from "../lib/discord";
import { SkeletonGrid } from "../components/Skeleton";
import { ErrorBanner } from "../components/ErrorBanner";

export function Guilds() {
  const [guilds, setGuilds] = useState<GuildSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .guilds()
      .then(setGuilds)
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <ErrorBanner message={`Failed to load servers: ${error}`} />;
  if (guilds === null) return <SkeletonGrid />;
  if (guilds.length === 0) {
    return (
      <p className="list-empty">
        You don't have Manage Server access on any server yet — ask a server admin to grant you access, or add the
        bot to a server you manage.
      </p>
    );
  }

  return (
    <div className="guild-grid">
      {guilds.map((guild) => {
        const icon = guildIconUrl(guild);
        return (
          <div className="guild-card" key={guild.id}>
            {icon ? (
              <img className="guild-icon" src={icon} alt="" />
            ) : (
              <div className="guild-icon guild-icon--placeholder">{guild.name[0]}</div>
            )}
            <div className="guild-name">{guild.name}</div>
            {guild.bot_present ? (
              <>
                <div className="guild-meta">{guild.member_count ?? "?"} members</div>
                <div className="guild-card-actions">
                  <Link className="button" to={`/guilds/${guild.id}`}>
                    Configure
                  </Link>
                  <Link className="button button--link" to={`/guilds/${guild.id}/setup`}>
                    First-time setup
                  </Link>
                </div>
              </>
            ) : (
              <div className="guild-meta guild-meta--muted">Bot not in this server</div>
            )}
          </div>
        );
      })}
    </div>
  );
}
