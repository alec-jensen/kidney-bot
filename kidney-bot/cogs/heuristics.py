# Heuristics engine cog — evaluates new joins and post-join behavior for
# bot/spam detection, triggers automated actions, and exposes admin commands.
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

from __future__ import annotations

import asyncio
import dataclasses
import io
import json
import logging
import re
import time
from datetime import timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

import discord
from discord import app_commands
from discord.ext import commands

from cogs.moderation_views import ReviewApproveItem, ReviewBanItem, ReviewKickItem, make_review_view
from utils.database import Schemas
from utils.heuristics_config import (
    ActionConfig, HeuristicsDefaults, SignalThresholds, SignalWeights,
    DEFAULTS,
)
from utils.heuristics_engine import HeuristicsEngine, HeuristicsResult, PostJoinState
from utils.kidney_bot import KidneyBot

if TYPE_CHECKING:
    from cogs.invite_tracking import InviteTracking

_URL_RE = re.compile(r'https?://', re.IGNORECASE)

# RESOLVED (brand-new account spam, no log/no action): the real bug was that a
# JoinTrack was only ever created when the join-time score already met
# alert_threshold. A pure new-account join (age + default avatar) scores well
# under 40, so no track existed and on_message() — which requires a track —
# silently no-oped on every message, never evaluating behavioral signals.
# Fixed by always creating a JoinTrack on join (see on_member_join) so
# behavioral scoring can run and combine with the join score for every member
# during the tracking window. Separately: mute/kick/ban are threshold=101
# (disabled) by default and alert/review require alert_channel/review_channel
# to be configured — both cases now log at INFO instead of failing silently.
# (The reported username entropy near-miss, e.g. "oifhqoi3hj1r5" at ~3.24 vs.
# the 3.3 threshold, is expected tuning behavior, not a bug.)

def _time_ago(ts: int, now: int) -> str:
    delta = now - ts
    if delta < 3600:
        return f"{max(0, delta // 60)}m ago"
    if delta < 86400:
        return f"{delta // 3600}h ago"
    return f"{delta // 86400}d ago"

# All public flag names we care about, split by sentiment
_POSITIVE_PUBLIC_FLAGS = (
    'spammer',
)
_TRUSTED_PUBLIC_FLAGS = (
    'staff', 'partner',
    'hypesquad', 'hypesquad_bravery', 'hypesquad_brilliance', 'hypesquad_balance',
    'bug_hunter', 'bug_hunter_level_2', 'discord_certified_moderator',
    'early_supporter', 'active_developer',
    'early_verified_bot_developer', 'verified_bot_developer',
)
_MEMBER_FLAGS_WE_CHECK = (
    'did_rejoin', 'completed_onboarding', 'bypasses_verification',
    'started_onboarding', 'automod_quarantined_username', 'automod_quarantined_guild_tag',
    'guest',
)


def _extract_public_flags(member: discord.Member) -> frozenset[str]:
    pf = member.public_flags
    return frozenset(
        name for name in _POSITIVE_PUBLIC_FLAGS + _TRUSTED_PUBLIC_FLAGS
        if getattr(pf, name, False)
    )


def _extract_member_flags(member: discord.Member) -> frozenset[str]:
    mf = getattr(member, 'flags', None)
    if mf is None:
        return frozenset()
    return frozenset(
        name for name in _MEMBER_FLAGS_WE_CHECK
        if getattr(mf, name, False)
    )


def _build_engine(guild_config: Schemas.GuildHeuristicsConfig) -> HeuristicsEngine:
    weights = (
        dataclasses.replace(DEFAULTS.weights, **guild_config.weight_overrides)
        if guild_config.weight_overrides else DEFAULTS.weights
    )
    thresholds = (
        dataclasses.replace(DEFAULTS.thresholds, **guild_config.threshold_overrides)
        if guild_config.threshold_overrides else DEFAULTS.thresholds
    )
    actions = (
        dataclasses.replace(DEFAULTS.actions, **guild_config.action_overrides)
        if guild_config.action_overrides else DEFAULTS.actions
    )
    cfg = HeuristicsDefaults(
        weights=weights, thresholds=thresholds, actions=actions,
        suspicious_username_patterns=DEFAULTS.suspicious_username_patterns,
        spam_keywords=DEFAULTS.spam_keywords,
    )
    return HeuristicsEngine(cfg)


def _is_enabled(guild_config: Schemas.GuildHeuristicsConfig) -> bool:
    return guild_config.enabled is True


def _action_color(action: str | None) -> discord.Color:
    return {
        "ban": discord.Color.dark_red(),
        "kick": discord.Color.red(),
        "rejoin_kick": discord.Color.red(),
        "mute": discord.Color.orange(),
    }.get(action or "", discord.Color.yellow())


class Heuristics(commands.Cog):
    def __init__(self, bot: KidneyBot) -> None:
        self.bot = bot
        self._expire_task: asyncio.Task | None = None

        # In-memory join tracking for clustering signals (avoids DB round-trips
        # for time-window counts). Entries are (timestamp,) tuples.
        # guild_id -> [(timestamp, avatar_hash | None), ...]
        self._recent_joins: dict[int, list[tuple[int, str | None]]] = {}

        # guild_id -> unix timestamp when elevated alert state expires.
        # Set by the network cog via the 'guild_elevated' event when a raid is
        # detected in a sibling server; lowers action thresholds while active.
        self._elevated_until: dict[int, int] = {}

    async def cog_load(self) -> None:
        self._expire_task = asyncio.create_task(self._expire_loop())
        self.bot.add_dynamic_items(ReviewApproveItem, ReviewKickItem, ReviewBanItem)

    async def cog_unload(self) -> None:
        if self._expire_task:
            self._expire_task.cancel()

    async def _expire_loop(self) -> None:
        while True:
            await asyncio.sleep(3600)
            try:
                now = int(time.time())
                expired, deleted = await self.bot.database.join_tracks.expire_and_get(now)
                if deleted:
                    logging.info(f"Heuristics: expired {deleted} stale join tracks")
                logging.debug(f"[heuristics] expire_loop: {len(expired)} tracks processed  {deleted} deleted")

                # Score decay: members whose tracking window ends without any incidents
                # are marked as trusted in the network reputation, reducing future suspicion.
                for track in expired:
                    if (
                        track.guild_id is None
                        or track.user_id is None
                        or track.kicked_for_verification
                        or track.mod_confirmed
                        or track.mod_false_positive
                        or (track.score or 0) <= 0
                    ):
                        continue
                    try:
                        ngc = await self.bot.database.network_guild_config.get(track.guild_id)
                        if not ngc or not ngc.network_id:
                            continue
                        rep = await self.bot.database.network_user_rep.get_user_rep(
                            ngc.network_id, track.user_id)
                        if rep is None:
                            continue
                        if track.guild_id not in rep.trusted_in_guilds:
                            rep.trusted_in_guilds.append(track.guild_id)
                        # If this guild was the source of a prior flag, clear it
                        if track.guild_id in rep.guilds_flagged:
                            rep.guilds_flagged.remove(track.guild_id)
                            rep.flag_count = max(0, rep.flag_count - 1)
                        await self.bot.database.network_user_rep.upsert_user_rep(rep)
                    except Exception:
                        logging.exception(
                            f"Heuristics: error updating trust decay for user {track.user_id}")
            except Exception:
                logging.exception("Heuristics: error in expire loop")

    # ── In-memory clustering ──────────────────────────────────────────────────

    def _record_join(
        self, guild_id: int, avatar_hash: str | None, now: int
    ) -> tuple[int, int]:
        """Record a join, prune stale entries, return (recent_count, same_avatar_count)."""
        window = DEFAULTS.thresholds.join_cluster_window_seconds
        entries = [
            (ts, h) for ts, h in self._recent_joins.get(guild_id, [])
            if ts >= now - window
        ]
        entries.append((now, avatar_hash))
        self._recent_joins[guild_id] = entries

        recent_count = len(entries)
        same_avatar = (
            sum(1 for _, h in entries if h is not None and h == avatar_hash)
            if avatar_hash else 0
        )
        return recent_count, same_avatar

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _invite_cog(self) -> InviteTracking | None:
        return self.bot.get_cog('InviteTracking')  # type: ignore[return-value]

    async def _guild_config(self, guild_id: int) -> Schemas.GuildHeuristicsConfig:
        cfg = await self.bot.database.heuristics_config.get(guild_id)
        return cfg or Schemas.GuildHeuristicsConfig(guild_id=guild_id)

    async def _staff_usernames(self, guild: discord.Guild) -> list[str]:
        names: list[str] = []
        for m in guild.members:
            if m.guild_permissions.kick_members or m.guild_permissions.ban_members:
                names.append(m.name)
                if m.nick:
                    names.append(m.nick)
        return names

    async def _post_review(
        self,
        guild: discord.Guild,
        member: discord.Member,
        result: HeuristicsResult,
        guild_config: Schemas.GuildHeuristicsConfig,
    ) -> None:
        """Post an actionable review card to the review channel for borderline joins."""
        channel_id = guild_config.review_channel_id
        if not channel_id:
            logging.info(
                f"Heuristics: {member} ({member.id}) scored {result.score} in "
                f"'{guild.name}' ({guild.id}) with no auto-action, but no review_channel "
                "is configured — nothing was posted. Set one with "
                "/heuristics review_channel.")
            return
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            logging.warning(
                f"Heuristics: configured review_channel_id={channel_id} in "
                f"'{guild.name}' ({guild.id}) is not a text channel/thread — "
                "review post skipped")
            return

        embed = discord.Embed(
            title=f"Review Queue: {member}",
            description=result.describe(),
            color=discord.Color.yellow(),
        )
        embed.add_field(name="User", value=f"{member.mention} (`{member.id}`)", inline=True)
        embed.add_field(
            name="Account Age",
            value=f"<t:{int(member.created_at.timestamp())}:R>",
            inline=True,
        )
        embed.add_field(name="Score", value=str(result.score), inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="No automated action was taken — review and decide below")
        try:
            await channel.send(embed=embed, view=make_review_view(member.id))
        except discord.Forbidden:
            logging.warning(f"Heuristics: can't post to review channel in {guild}")

    async def _send_alert(
        self,
        guild: discord.Guild,
        member: discord.Member,
        result: HeuristicsResult,
        guild_config: Schemas.GuildHeuristicsConfig,
        action_taken: str | None,
    ) -> None:
        channel_id = guild_config.alert_channel_id
        if not channel_id:
            logging.info(
                f"Heuristics: {member} ({member.id}) scored {result.score} in "
                f"'{guild.name}' ({guild.id}) (action_taken={action_taken!r}), but no "
                "alert_channel is configured — alert not delivered. Set one with "
                "/heuristics alert_channel.")
            return
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            logging.warning(
                f"Heuristics: configured alert_channel_id={channel_id} in "
                f"'{guild.name}' ({guild.id}) is not a text channel/thread — "
                "alert not delivered")
            return

        embed = discord.Embed(
            title=f"Suspicious Join: {member}",
            description=result.describe(),
            color=_action_color(action_taken),
        )
        embed.add_field(name="User", value=f"{member.mention} (`{member.id}`)", inline=True)
        embed.add_field(
            name="Account Age",
            value=f"<t:{int(member.created_at.timestamp())}:R>",
            inline=True,
        )
        if action_taken:
            embed.add_field(
                name="Action Taken",
                value=action_taken.replace('_', ' ').title(),
                inline=True,
            )
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)

    async def _take_action(
        self,
        member: discord.Member,
        score: int,
        guild_config: Schemas.GuildHeuristicsConfig,
        actions: ActionConfig,
    ) -> str | None:
        overrides: dict = guild_config.action_overrides or {}
        ban_t = overrides.get('ban_threshold', actions.ban_threshold)
        kick_t = overrides.get('kick_threshold', actions.kick_threshold)
        mute_t = overrides.get('mute_threshold', actions.mute_threshold)
        logging.debug(f"[heuristics] _take_action: {member} score={score} vs mute>={mute_t} kick>={kick_t} ban>={ban_t}")

        if score >= ban_t:
            delete_seconds = 0
            if guild_config.auto_delete_on_ban:
                delete_threshold = guild_config.auto_delete_score_threshold
                if delete_threshold is None or score >= delete_threshold:
                    delete_seconds = guild_config.auto_delete_seconds or 86400
            try:
                await member.ban(
                    reason=f"Heuristics auto-action: score {score}/100",
                    delete_message_seconds=delete_seconds,
                )
                logging.debug(
                    f"[heuristics] auto-ban {member} delete_seconds={delete_seconds}")
                return "ban"
            except discord.Forbidden:
                logging.warning(
                    f"Heuristics: no permission to ban {member} in {member.guild}")

        if score >= kick_t:
            try:
                await member.kick(reason=f"Heuristics auto-action: score {score}/100")
                return "kick"
            except discord.Forbidden:
                logging.warning(
                    f"Heuristics: no permission to kick {member} in {member.guild}")

        if score >= mute_t:
            try:
                await member.timeout(
                    timedelta(hours=24),
                    reason=f"Heuristics auto-action: score {score}/100",
                )
                return "mute"
            except discord.Forbidden:
                logging.warning(
                    f"Heuristics: no permission to timeout {member} in {member.guild}")

        return None

    # ── Event listeners ───────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_elevated(self, guild_id: int, duration: int) -> None:
        """Network cog dispatches this when a sibling server detects a raid."""
        self._elevated_until[guild_id] = int(time.time()) + duration
        logging.info(
            f"Heuristics: guild {guild_id} elevated for {duration}s (network raid alert)")

    @commands.Cog.listener()
    async def on_modlog_entry(
        self, entry: Schemas.ModLogEntry, guild: discord.Guild
    ) -> None:
        """Feedback loop: when a mod manually acts on a flagged member, record confirmation."""
        if entry.moderator_id == guild.me.id:
            return  # Bot's own action — not a manual confirmation
        if entry.action_type not in ("ban", "kick", "mute", "tempmute", "warn"):
            return
        if not entry.user_id or not entry.guild_id:
            return
        try:
            track = await self.bot.database.join_tracks.get_user_track(
                entry.guild_id, entry.user_id)
            if track and not track.mod_confirmed and (track.score or 0) > 0:
                track.mod_confirmed = True
                await self.bot.database.join_tracks.upsert_for_member(track)
        except Exception:
            logging.exception(f"Heuristics: error recording mod confirmation for {entry.user_id}")

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        """Feedback loop: when a mod unbans someone the bot banned, flag as false positive."""
        try:
            history = await self.bot.database.mod_log.get_user_history(user.id, guild.id)
            bot_ban = next(
                (e for e in reversed(history)
                 if e.action_type == "ban" and e.moderator_id == guild.me.id),
                None,
            )
            if bot_ban is None:
                return
            track = await self.bot.database.join_tracks.get_user_track(guild.id, user.id)
            if track and not track.mod_false_positive:
                track.mod_false_positive = True
                await self.bot.database.join_tracks.upsert_for_member(track)
                logging.info(f"Heuristics: false positive recorded for {user.id} in {guild.id}")
        except Exception:
            logging.exception(f"Heuristics: error recording false positive for {user}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return

        guild_config = await self._guild_config(member.guild.id)
        if not _is_enabled(guild_config):
            logging.debug(
                f"[heuristics] join: engine disabled for '{member.guild.name}' "
                f"({member.guild.id}) — skipping {member} ({member.id})")
            return

        logging.debug(f"[heuristics] join: {member} ({member.id}) in '{member.guild.name}' ({member.guild.id})")

        # Wait for InviteTracking's on_member_join to finish its guild.invites() call
        await asyncio.sleep(1.0)

        now = int(time.time())

        # ── Collect all data Discord gives us ─────────────────────────────────
        avatar_hash = member.avatar.key if member.avatar else None
        avatar_is_animated = member.avatar.is_animated() if member.avatar else False

        public_flags = _extract_public_flags(member)
        member_flags = _extract_member_flags(member)
        premium_since = int(member.premium_since.timestamp()) if member.premium_since else None

        invite_cog = self._invite_cog()
        invite_code = (
            invite_cog.get_used_invite_code(member.guild.id, member.id)
            if invite_cog else None
        )
        if invite_cog:
            invite_cog.clear_used_invite(member.guild.id, member.id)

        inviter_id: int | None = None
        invite_creator_history_count = 0
        if invite_code and invite_cog:
            inviter_id = invite_cog.get_invite_creator_id(member.guild.id, invite_code)
            if inviter_id:
                creator_history = await self.bot.database.mod_log.get_user_history(
                    inviter_id, member.guild.id)
                invite_creator_history_count = len(creator_history)

        existing_modlog = await self.bot.database.mod_log.get_user_history(
            member.id, member.guild.id)

        existing_track = await self.bot.database.join_tracks.get_user_track(
            member.guild.id, member.id)
        kicked_for_verification = (
            existing_track.kicked_for_verification is True if existing_track else False
        )

        # In-memory clustering (accurate — tracks ALL joins, not just scored ones)
        recent_join_count, recent_same_avatar_count = self._record_join(
            member.guild.id, avatar_hash, now)

        staff_names = await self._staff_usernames(member.guild)
        engine = _build_engine(guild_config)

        # Dispatch raid alert exactly when join count first crosses the cluster threshold
        if recent_join_count == engine.config.thresholds.join_cluster_min_count:
            self.bot.dispatch('raid_alert', member.guild, recent_join_count)

        # ── Network cross-server context ───────────────────────────────────────
        network_prior_flag_count = 0
        network_trusted = False
        try:
            ngc = await self.bot.database.network_guild_config.get(member.guild.id)
            if ngc and ngc.network_id:
                rep = await self.bot.database.network_user_rep.get_user_rep(
                    ngc.network_id, member.id)
                if rep:
                    network_prior_flag_count = rep.flag_count
                    network_trusted = member.guild.id in rep.trusted_in_guilds

                # Watchlist: alert immediately if this user is being watched
                network_obj = await self.bot.database.networks.get(ngc.network_id)
                if network_obj:
                    wl_entry = next(
                        (w for w in network_obj.watchlist if w.get('user_id') == member.id),
                        None)
                    if wl_entry:
                        self.bot.dispatch(
                            'watchlist_hit', member.guild, member, wl_entry, network_obj)
        except Exception:
            logging.exception(f"Heuristics: error fetching network context for {member}")

        logging.debug(
            f"[heuristics] join data: public_flags={set(public_flags) or '(none)'}  "
            f"member_flags={set(member_flags) or '(none)'}  animated={avatar_is_animated}  "
            f"invite={invite_code!r}  inviter={inviter_id}  "
            f"creator_history={invite_creator_history_count}  "
            f"recent_joins={recent_join_count}  same_avatar={recent_same_avatar_count}  "
            f"network_flags={network_prior_flag_count}  network_trusted={network_trusted}"
        )
        result = engine.evaluate_join(
            user_id=member.id,
            guild_id=member.guild.id,
            account_created_at=int(member.created_at.timestamp()),
            username=member.name,
            global_name=member.global_name,
            has_avatar=member.avatar is not None,
            avatar_is_animated=avatar_is_animated,
            avatar_hash=avatar_hash,
            public_flags=public_flags,
            member_flags=member_flags,
            premium_since=premium_since,
            invite_code=invite_code,
            invite_creator_history_count=invite_creator_history_count,
            recent_join_count=recent_join_count,
            recent_same_avatar_count=recent_same_avatar_count,
            staff_usernames=staff_names,
            existing_modlog_count=len(existing_modlog),
            kicked_for_verification=kicked_for_verification,
            network_prior_flag_count=network_prior_flag_count,
            network_trusted=network_trusted,
        )

        logging.debug(f"[heuristics] score: {result.score}/100  ({len(result.signals)} signals)")
        for _s in result.signals:
            _sign = '+' if _s.score_delta >= 0 else ''
            logging.debug(f"[heuristics]   {_sign}{_s.score_delta:>3}  {_s.signal_id}  - {_s.detail}")
        actions = engine.config.actions
        overrides: dict = guild_config.action_overrides or {}
        alert_t = overrides.get('alert_threshold', actions.alert_threshold)
        rejoin_kick_t = overrides.get('rejoin_kick_threshold', actions.rejoin_kick_threshold)
        kick_t = overrides.get('kick_threshold', actions.kick_threshold)
        tracking_days = guild_config.tracking_days or actions.tracking_days
        action_taken: str | None = None

        # Lower all thresholds by 15 points if guild is under elevated raid alert
        if self._elevated_until.get(member.guild.id, 0) > now:
            alert_t = max(0, alert_t - 15)
            rejoin_kick_t = max(0, rejoin_kick_t - 15)
            kick_t = max(0, kick_t - 15)

        # Rejoin-to-verify kick — only offered once per user, only in the band
        # [rejoin_kick_threshold, kick_threshold). Above kick_threshold we go
        # straight to a normal kick or ban.
        if (
            not kicked_for_verification
            and actions.rejoin_verify_enabled
            and rejoin_kick_t <= result.score < kick_t
        ):
            try:
                invite_url = (
                    f"https://discord.gg/{member.guild.vanity_url_code}"
                    if member.guild.vanity_url_code else member.guild.name
                )
                try:
                    await member.send(
                        f"You were temporarily removed from **{member.guild.name}** "
                        f"for automated verification. Rejoining will confirm you're a "
                        f"real person: {invite_url}"
                    )
                except (discord.Forbidden, discord.HTTPException):
                    pass

                await member.kick(
                    reason=f"Heuristics: score {result.score}/100 — rejoin to verify")
                action_taken = "rejoin_kick"

                track = Schemas.JoinTrack(
                    id=str(uuid4()),
                    guild_id=member.guild.id,
                    user_id=member.id,
                    joined_at=now,
                    expires_at=now + int(actions.rejoin_verify_window_hours * 3600),
                    score=result.score,
                    signals=[
                        {"id": s.signal_id, "delta": s.score_delta, "detail": s.detail}
                        for s in result.signals
                    ],
                    invite_code=invite_code,
                    inviter_id=inviter_id,
                    kicked_for_verification=True,
                )
                await self.bot.database.join_tracks.upsert_for_member(track)
            except discord.Forbidden:
                logging.warning(
                    f"Heuristics: no permission to kick {member} in {member.guild}")

        # Normal thresholds (skip if already acted)
        if action_taken is None:
            action_taken = await self._take_action(
                member, result.score, guild_config, actions)

        logging.debug(f"[heuristics] action_taken={action_taken!r} score={result.score} alert_t={alert_t}")

        # Save a tracking record for EVERY join (regardless of join-time score) so we can:
        # - populate the invite tree via inviter_id
        # - record feedback (mod_confirmed / mod_false_positive)
        # - let on_message's behavioral scoring run — it requires an existing JoinTrack,
        #   so a brand-new account that scores under alert_threshold at join time (e.g.
        #   new-account + default-avatar signals alone) but then immediately spams would
        #   otherwise never be tracked, and its behavioral signals would never be
        #   evaluated or combined with the join score. See resolution note above.
        # Banned/kicked members get a short 3-day window (they aren't being monitored);
        # others get the full tracking_days window for behavioral scoring.
        if action_taken != "rejoin_kick":
            track_expiry = (
                now + 3 * 86400
                if action_taken in ("ban", "kick") else
                now + tracking_days * 86400
            )
            track = Schemas.JoinTrack(
                id=str(uuid4()),
                guild_id=member.guild.id,
                user_id=member.id,
                joined_at=now,
                expires_at=track_expiry,
                score=result.score,
                signals=[
                    {"id": s.signal_id, "delta": s.score_delta, "detail": s.detail}
                    for s in result.signals
                ],
                invite_code=invite_code,
                inviter_id=inviter_id,
            )
            await self.bot.database.join_tracks.upsert_for_member(track)
            logging.debug(f"[heuristics] track saved  expires_in={track_expiry - now}s  inviter={inviter_id}")

        if result.score >= alert_t:
            await self._send_alert(
                member.guild, member, result, guild_config, action_taken)
            # Post to review queue when flagged but no auto-action was taken (borderline)
            if action_taken is None:
                await self._post_review(member.guild, member, result, guild_config)

            # Update shared network user reputation for this member
            try:
                ngc = await self.bot.database.network_guild_config.get(member.guild.id)
                if ngc and ngc.network_id:
                    rep = await self.bot.database.network_user_rep.get_user_rep(
                        ngc.network_id, member.id)
                    if rep is None:
                        rep = Schemas.NetworkUserRep(
                            network_id=ngc.network_id, user_id=member.id)
                    rep.flag_count += 1
                    rep.last_flagged_at = now
                    if member.guild.id not in rep.guilds_flagged:
                        rep.guilds_flagged.append(member.guild.id)
                    if action_taken in ("ban", "kick", "mute", "rejoin_kick"):
                        rep.action_count += 1
                    await self.bot.database.network_user_rep.upsert_user_rep(rep)
            except Exception:
                logging.exception(f"Heuristics: error updating network rep for {member}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        if not isinstance(message.author, discord.Member):
            return

        now = int(time.time())
        track = await self.bot.database.join_tracks.get_user_track(
            message.guild.id, message.author.id)

        if track is None or track.expires_at is None or track.expires_at <= now:
            return
        if track.kicked_for_verification:
            return

        guild_config = await self._guild_config(message.guild.id)
        if not _is_enabled(guild_config):
            logging.debug(
                f"[heuristics] msg: engine disabled for '{message.guild.name}' "
                f"({message.guild.id}) — skipping tracked user {message.author.id}")
            return

        logging.debug(
            f"[heuristics] msg: {message.author} ({message.author.id}) "
            f"msg#{track.message_count + 1}  join_score={track.score}")

        has_links = bool(_URL_RE.search(message.content))
        mention_count = len(message.mentions)
        role_mention_count = len(message.role_mentions)
        mention_everyone = message.mention_everyone
        attachment_count = len(message.attachments)
        first_message_at = track.first_message_at or now

        state = PostJoinState(
            message_count=track.message_count,
            channels_messaged=list(track.channels_messaged),
            first_message_at=first_message_at,
            total_mentions=track.total_mentions,
        )

        engine = _build_engine(guild_config)
        msg_result = engine.evaluate_message(
            user_id=message.author.id,
            guild_id=message.guild.id,
            state=state,
            content=message.content,
            channel_id=message.channel.id,
            mention_count=mention_count,
            role_mention_count=role_mention_count,
            mention_everyone=mention_everyone,
            has_links=has_links,
            attachment_count=attachment_count,
            now=now,
        )

        # Update tracking record. behavioral_score REPLACES the previous value
        # (not additive) — so the score reflects current behaviour, not all past
        # messages. The join_score (track.score) is permanent.
        # Store channel+timestamp to enable time-window filtering for multi_channel_spam.
        seen = {ch_id for ch_id, _ in track.channels_messaged}
        if message.channel.id not in seen:
            track.channels_messaged.append((message.channel.id, now))
        track.message_count += 1
        track.first_message_at = first_message_at
        track.total_mentions += mention_count + (1 if mention_everyone else 0)
        track.behavioral_score = msg_result.score  # replace, not accumulate
        await self.bot.database.join_tracks.upsert_for_member(track)

        # Effective score = join score + current behavioral score
        combined_score = min(100, (track.score or 0) + msg_result.score)
        if msg_result.score > 0:
            logging.debug(
                f"[heuristics] behavioral: {message.author} behavioral_score={msg_result.score} "
                f"join_score={track.score or 0} combined={combined_score}  "
                f"signals=[{', '.join(_s.signal_id for _s in msg_result.signals)}]")
            action_taken = await self._take_action(
                message.author, combined_score, guild_config, engine.config.actions)
            if action_taken:
                await self._send_alert(
                    message.guild, message.author, msg_result, guild_config, action_taken)

    # ── /scan command ─────────────────────────────────────────────────────────

    @app_commands.command(
        name="scan",
        description="Run the heuristics engine on a server member on demand")
    @app_commands.checks.has_permissions(kick_members=True)
    async def scan(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if interaction.guild is None:
            return
        await interaction.response.defer(ephemeral=True)

        guild_config = await self._guild_config(interaction.guild.id)
        engine = _build_engine(guild_config)
        staff_names = await self._staff_usernames(interaction.guild)

        existing_track = await self.bot.database.join_tracks.get_user_track(
            interaction.guild.id, member.id)
        existing_modlog = await self.bot.database.mod_log.get_user_history(
            member.id, interaction.guild.id)

        avatar_hash = member.avatar.key if member.avatar else None
        avatar_is_animated = member.avatar.is_animated() if member.avatar else False

        result = engine.evaluate_join(
            user_id=member.id,
            guild_id=interaction.guild.id,
            account_created_at=int(member.created_at.timestamp()),
            username=member.name,
            global_name=member.global_name,
            has_avatar=member.avatar is not None,
            avatar_is_animated=avatar_is_animated,
            avatar_hash=avatar_hash,
            public_flags=_extract_public_flags(member),
            member_flags=_extract_member_flags(member),
            premium_since=(
                int(member.premium_since.timestamp()) if member.premium_since else None
            ),
            staff_usernames=staff_names,
            existing_modlog_count=len(existing_modlog),
            kicked_for_verification=(
                existing_track.kicked_for_verification is True
                if existing_track else False
            ),
        )

        embed = discord.Embed(
            title=f"Heuristics Scan: {member}",
            description=result.describe(),
            color=_action_color(None),
        )
        embed.add_field(
            name="Account Created",
            value=f"<t:{int(member.created_at.timestamp())}:R>",
            inline=True,
        )
        embed.add_field(
            name="Booster",
            value="Yes" if member.premium_since else "No",
            inline=True,
        )
        if existing_track:
            behavioral = existing_track.behavioral_score
            total = min(100, (existing_track.score or 0) + behavioral)
            embed.add_field(
                name="Tracked Score",
                value=f"Join: {existing_track.score} + Behavioral: {behavioral} = **{total}**",
                inline=False,
            )
            embed.add_field(
                name="Tracking Expires",
                value=(
                    f"<t:{existing_track.expires_at}:R>"
                    if existing_track.expires_at else "—"
                ),
                inline=True,
            )
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /heuristics config group ──────────────────────────────────────────────

    heuristics_group = app_commands.Group(
        name="heuristics",
        description="Configure the heuristics engine for this server",
    )

    @heuristics_group.command(
        name="enable", description="Enable or disable the heuristics engine")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def heuristics_enable(
        self, interaction: discord.Interaction, enabled: bool
    ) -> None:
        if interaction.guild is None:
            return
        cfg = await self._guild_config(interaction.guild.id)
        cfg.enabled = enabled
        await self.bot.database.heuristics_config.save(cfg)
        await interaction.response.send_message(
            f"Heuristics engine {'enabled' if enabled else 'disabled'}.", ephemeral=True)

    @heuristics_group.command(
        name="alert_channel",
        description="Set the channel where suspicious join alerts are sent")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def heuristics_alert_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel,
    ) -> None:
        if interaction.guild is None:
            return
        cfg = await self._guild_config(interaction.guild.id)
        cfg.alert_channel_id = channel.id
        await self.bot.database.heuristics_config.save(cfg)
        await interaction.response.send_message(
            f"Alert channel set to {channel.mention}.", ephemeral=True)

    @heuristics_group.command(
        name="tracking_days",
        description="How many days to monitor new members after joining (default 7)")
    @app_commands.describe(days="Number of days to track (1–30)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def heuristics_tracking_days(
        self, interaction: discord.Interaction, days: int
    ) -> None:
        if interaction.guild is None:
            return
        if not 1 <= days <= 30:
            await interaction.response.send_message(
                "Days must be between 1 and 30.", ephemeral=True)
            return
        cfg = await self._guild_config(interaction.guild.id)
        cfg.tracking_days = days
        await self.bot.database.heuristics_config.save(cfg)
        await interaction.response.send_message(
            f"Tracking window set to {days} day(s).", ephemeral=True)

    @heuristics_group.command(
        name="thresholds",
        description="View or set the score thresholds that trigger each automated action")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        alert="Alert-only threshold (default 40)",
        mute="24-hour timeout threshold (default 101, disabled — lower to enable)",
        kick="Kick threshold (default 101, disabled — lower to enable)",
        ban="Immediate ban threshold (default 101, disabled — lower to enable)",
    )
    async def heuristics_thresholds(
        self,
        interaction: discord.Interaction,
        alert: int | None = None,
        mute: int | None = None,
        kick: int | None = None,
        ban: int | None = None,
    ) -> None:
        if interaction.guild is None:
            return
        cfg = await self._guild_config(interaction.guild.id)
        overrides: dict = dict(cfg.action_overrides or {})
        if alert is not None:
            overrides['alert_threshold'] = alert
        if mute is not None:
            overrides['mute_threshold'] = mute
        if kick is not None:
            overrides['kick_threshold'] = kick
        if ban is not None:
            overrides['ban_threshold'] = ban
        cfg.action_overrides = overrides or None
        await self.bot.database.heuristics_config.save(cfg)

        effective = (
            dataclasses.replace(DEFAULTS.actions, **overrides)
            if overrides else DEFAULTS.actions
        )
        embed = discord.Embed(title="Heuristics Thresholds", color=discord.Color.blurple())
        embed.add_field(name="Alert", value=str(effective.alert_threshold), inline=True)
        embed.add_field(name="Mute", value=str(effective.mute_threshold), inline=True)
        embed.add_field(name="Kick", value=str(effective.kick_threshold), inline=True)
        embed.add_field(name="Ban", value=str(effective.ban_threshold), inline=True)
        embed.add_field(
            name="Rejoin-verify Kick", value=str(effective.rejoin_kick_threshold), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @heuristics_group.command(
        name="thresholds_reset",
        description="Reset all action thresholds to their defaults")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def heuristics_thresholds_reset(
        self, interaction: discord.Interaction
    ) -> None:
        if interaction.guild is None:
            return
        cfg = await self._guild_config(interaction.guild.id)
        overrides = dict(cfg.action_overrides or {})
        for key in (
            'alert_threshold', 'mute_threshold', 'kick_threshold',
            'ban_threshold', 'rejoin_kick_threshold',
        ):
            overrides.pop(key, None)
        cfg.action_overrides = overrides or None
        await self.bot.database.heuristics_config.save(cfg)
        await interaction.response.send_message(
            "Action thresholds reset to defaults.", ephemeral=True)

    @heuristics_group.command(
        name="weights_export",
        description="Download the current signal weights as a JSON file")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def heuristics_weights_export(
        self, interaction: discord.Interaction
    ) -> None:
        if interaction.guild is None:
            return
        cfg = await self._guild_config(interaction.guild.id)
        engine = _build_engine(cfg)
        data = json.dumps(dataclasses.asdict(engine.config.weights), indent=2)
        await interaction.response.send_message(
            "Current signal weights:",
            file=discord.File(io.BytesIO(data.encode()), filename="weights.json"),
            ephemeral=True,
        )

    @heuristics_group.command(
        name="weights_import",
        description="Upload a JSON file to override signal weights for this server")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def heuristics_weights_import(
        self, interaction: discord.Interaction, file: discord.Attachment
    ) -> None:
        if interaction.guild is None:
            return
        if not file.filename.endswith('.json'):
            await interaction.response.send_message(
                "File must be a .json file.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            overrides = json.loads(await file.read())
        except json.JSONDecodeError as e:
            await interaction.followup.send(f"Invalid JSON: {e}", ephemeral=True)
            return
        valid_fields = {f.name for f in dataclasses.fields(SignalWeights)}
        bad_keys = [k for k in overrides if k not in valid_fields]
        if bad_keys:
            await interaction.followup.send(
                f"Unknown weight fields: {', '.join(bad_keys)}", ephemeral=True)
            return
        cfg = await self._guild_config(interaction.guild.id)
        cfg.weight_overrides = overrides or None
        await self.bot.database.heuristics_config.save(cfg)
        await interaction.followup.send(
            f"Imported {len(overrides)} weight override(s).", ephemeral=True)

    @heuristics_group.command(
        name="weights_reset",
        description="Remove all signal weight overrides and restore defaults")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def heuristics_weights_reset(
        self, interaction: discord.Interaction
    ) -> None:
        if interaction.guild is None:
            return
        cfg = await self._guild_config(interaction.guild.id)
        cfg.weight_overrides = None
        await self.bot.database.heuristics_config.save(cfg)
        await interaction.response.send_message(
            "Signal weights reset to defaults.", ephemeral=True)

    @heuristics_group.command(
        name="review_channel",
        description="Set the channel where borderline joins are posted for mod review")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def heuristics_review_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        if interaction.guild is None:
            return
        cfg = await self._guild_config(interaction.guild.id)
        cfg.review_channel_id = channel.id
        await self.bot.database.heuristics_config.save(cfg)
        await interaction.response.send_message(
            f"Review channel set to {channel.mention}. "
            "Joins that score above the alert threshold but trigger no auto-action "
            "will be posted there with Approve / Kick / Ban buttons.",
            ephemeral=True,
        )

    @heuristics_group.command(
        name="auto_delete",
        description="Configure automatic message deletion on heuristics auto-bans (disabled by default)")
    @app_commands.describe(
        enabled="Whether to auto-delete message history when the engine auto-bans someone",
        window_hours="How many hours of history to delete (1-168, default 24)",
        score_threshold="Only auto-delete if the score is at least this high (default: same as ban threshold)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def heuristics_auto_delete(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        window_hours: app_commands.Range[int, 1, 168] | None = None,
        score_threshold: int | None = None,
    ) -> None:
        if interaction.guild is None:
            return
        cfg = await self._guild_config(interaction.guild.id)
        cfg.auto_delete_on_ban = enabled
        if window_hours is not None:
            cfg.auto_delete_seconds = window_hours * 3600
        if score_threshold is not None:
            cfg.auto_delete_score_threshold = score_threshold
        await self.bot.database.heuristics_config.save(cfg)

        if not enabled:
            await interaction.response.send_message(
                "Auto-delete on ban disabled.", ephemeral=True)
            return

        hours = (cfg.auto_delete_seconds or 86400) // 3600
        threshold_desc = (
            f"score ≥ {cfg.auto_delete_score_threshold}"
            if cfg.auto_delete_score_threshold is not None
            else "any auto-ban"
        )
        await interaction.response.send_message(
            f"Auto-delete on ban enabled. Deletes the last {hours} hour(s) of message "
            f"history for {threshold_desc}.",
            ephemeral=True,
        )

    @heuristics_group.command(
        name="stats",
        description="Show heuristics detection statistics for this server")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def heuristics_stats(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        await interaction.response.defer(ephemeral=True)

        now = int(time.time())
        since_30d = now - 30 * 86400
        since_7d = now - 7 * 86400

        tracks = await self.bot.database.join_tracks.get_recent_joins(
            interaction.guild.id, since_30d)
        auto_actions = await self.bot.database.mod_log.query_many({
            "guild_id": interaction.guild.id,
            "moderator_id": interaction.guild.me.id,
            "timestamp": {"$gte": since_30d},
        })

        total_30d = len(tracks)
        total_7d = sum(1 for t in tracks if t.joined_at and t.joined_at >= since_7d)
        confirmed = sum(1 for t in tracks if t.mod_confirmed)
        false_pos = sum(1 for t in tracks if t.mod_false_positive)
        rejoin_kicks = sum(1 for t in tracks if t.kicked_for_verification)

        action_counts: dict[str, int] = {}
        for entry in auto_actions:
            at = entry.action_type or "unknown"
            action_counts[at] = action_counts.get(at, 0) + 1

        embed = discord.Embed(
            title="Heuristics Statistics (last 30 days)",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Flagged joins (30d)", value=str(total_30d), inline=True)
        embed.add_field(name="Flagged joins (7d)", value=str(total_7d), inline=True)
        embed.add_field(name="​", value="​", inline=True)

        action_lines = [
            f"Auto-ban: {action_counts.get('ban', 0)}",
            f"Auto-kick: {action_counts.get('kick', 0)}",
            f"Auto-mute: {action_counts.get('mute', 0)}",
            f"Rejoin-verify: {rejoin_kicks}",
        ]
        embed.add_field(name="Automated actions", value="\n".join(action_lines), inline=True)

        accuracy_lines = [
            f"Mod confirmed ✓: {confirmed}",
            f"False positives ✗: {false_pos}",
        ]
        if confirmed + false_pos > 0:
            precision = confirmed / (confirmed + false_pos) * 100
            accuracy_lines.append(f"Precision: {precision:.0f}%")
        embed.add_field(name="Feedback", value="\n".join(accuracy_lines), inline=True)
        embed.set_footer(text="Precision = confirmed / (confirmed + false positives)")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @heuristics_group.command(
        name="status",
        description="Show the current heuristics configuration for this server")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def heuristics_status(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        cfg = await self._guild_config(interaction.guild.id)
        engine = _build_engine(cfg)
        actions = engine.config.actions
        alert_ch = (
            f"<#{cfg.alert_channel_id}>" if cfg.alert_channel_id else "Not set"
        )
        embed = discord.Embed(
            title="Heuristics Engine Status", color=discord.Color.blurple())
        embed.add_field(
            name="Enabled", value="Yes" if _is_enabled(cfg) else "No", inline=True)
        review_ch = f"<#{cfg.review_channel_id}>" if cfg.review_channel_id else "Not set"
        embed.add_field(name="Alert Channel", value=alert_ch, inline=True)
        embed.add_field(name="Review Channel", value=review_ch, inline=True)
        embed.add_field(
            name="Tracking Window",
            value=f"{cfg.tracking_days or actions.tracking_days} days", inline=True)
        embed.add_field(name="Alert Threshold", value=str(actions.alert_threshold), inline=True)
        embed.add_field(name="Mute Threshold", value=str(actions.mute_threshold), inline=True)
        embed.add_field(name="Kick Threshold", value=str(actions.kick_threshold), inline=True)
        embed.add_field(name="Ban Threshold", value=str(actions.ban_threshold), inline=True)
        embed.add_field(
            name="Rejoin-to-Verify",
            value=(
                f"Enabled (>= {actions.rejoin_kick_threshold}, "
                f"{actions.rejoin_verify_window_hours}h window)"
                if actions.rejoin_verify_enabled else "Disabled"
            ),
            inline=False,
        )
        embed.add_field(
            name="Weight Overrides",
            value=(
                f"{len(cfg.weight_overrides)} fields"
                if cfg.weight_overrides else "None (defaults)"
            ),
            inline=True,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: KidneyBot) -> None:
    await bot.add_cog(Heuristics(bot))
