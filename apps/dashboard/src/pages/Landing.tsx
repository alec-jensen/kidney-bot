import { Link } from "react-router-dom";
import { loginUrl } from "../lib/api";

const FEATURES = [
  {
    title: "All-in-one moderation",
    body: "Warnings, mutes, kicks, bans, and escalation rules that suggest the next action based on a member's history.",
  },
  {
    title: "Anti-bot heuristics",
    body: "Score new members on join behavior and account signals to catch raids and bots before they cause damage.",
  },
  {
    title: "Honeypots",
    body: "Decoy channels that quietly flag or remove anyone who takes the bait.",
  },
  {
    title: "Cross-server networks",
    body: "Share bans and watchlists across a network of servers you trust, plus invite tracking to see how members arrive.",
  },
];

export function Landing() {
  return (
    <div className="landing">
      <section className="landing-hero">
        <h1>kidney bot</h1>
        <p className="landing-pitch">
          An all-in-one moderation bot for Discord — moderation tooling, anti-bot heuristics, honeypots, cross-server
          networks, invite tracking, and a web dashboard to configure it all without touching a single slash
          command.
        </p>
        <div className="landing-actions">
          <a className="button" href={loginUrl()}>
            Login with Discord
          </a>
          <Link className="button button--secondary" to="/docs/commands">
            Command docs
          </Link>
        </div>
      </section>

      <section className="landing-features">
        {FEATURES.map((feature) => (
          <div className="feature-card" key={feature.title}>
            <h3>{feature.title}</h3>
            <p>{feature.body}</p>
          </div>
        ))}
      </section>
    </div>
  );
}
