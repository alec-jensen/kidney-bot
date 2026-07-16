import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type GuildSummary } from "../lib/api";
import { useDirty } from "../lib/dirty";

interface GuildSwitcherProps {
  currentGuildId: string;
}

/** Compact dropdown for jumping to another bot_present server's settings without going back to the grid. */
export function GuildSwitcher({ currentGuildId }: GuildSwitcherProps) {
  const [guilds, setGuilds] = useState<GuildSummary[] | null>(null);
  const navigate = useNavigate();
  const { guardNavigation } = useDirty();

  useEffect(() => {
    api
      .guilds()
      .then((all) => setGuilds(all.filter((g) => g.bot_present)))
      .catch(() => setGuilds(null));
  }, []);

  if (!guilds || guilds.length <= 1) return null;

  function handleChange(guildId: string) {
    if (guildId === currentGuildId) return;
    guardNavigation(() => navigate(`/guilds/${guildId}`));
  }

  return (
    <select
      className="guild-switcher"
      value={currentGuildId}
      onChange={(e) => handleChange(e.target.value)}
      aria-label="Switch server"
    >
      {guilds.map((g) => (
        <option key={g.id} value={g.id}>
          {g.name}
        </option>
      ))}
    </select>
  );
}
