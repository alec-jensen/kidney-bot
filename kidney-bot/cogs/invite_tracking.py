# Invite tracking — snapshots guild invites and diffs on member_join to identify
# which invite a new member used.  Exposes /invites commands for staff.
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

from __future__ import annotations

import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

from utils.database import Schemas
from utils.kidney_bot import KidneyBot


def _time_ago(ts: int, now: int) -> str:
    delta = now - ts
    if delta < 3600:
        return f"{max(0, delta // 60)}m ago"
    if delta < 86400:
        return f"{delta // 3600}h ago"
    return f"{delta // 86400}d ago"


class InviteTracking(commands.Cog):
    def __init__(self, bot: KidneyBot) -> None:
        self.bot = bot
        # guild_id -> {code: uses}
        self._snapshots: dict[int, dict[str, int]] = {}
        # guild_id -> {code: inviter_id}
        self._creators: dict[int, dict[str, int]] = {}
        # (guild_id, member_id) -> (invite_code | None, timestamp)
        # Stored with a timestamp so stale entries can be pruned automatically.
        self._last_used: dict[tuple[int, int], tuple[str | None, int]] = {}

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _snapshot_guild(self, guild: discord.Guild) -> None:
        try:
            invites = await guild.invites()
            self._snapshots[guild.id] = {inv.code: inv.uses or 0 for inv in invites}
            self._creators[guild.id] = {
                inv.code: inv.inviter.id
                for inv in invites
                if inv.inviter is not None
            }
        except discord.Forbidden:
            pass
        except Exception:
            logging.exception(f"Failed to snapshot invites for guild {guild.id}")

    async def _guild_config(self, guild_id: int) -> Schemas.GuildConfig:
        cfg = await self.bot.database.guild_config.get(guild_id)
        if cfg is None:
            cfg = Schemas.GuildConfig(guild_id=guild_id)
        return cfg

    # ── Listeners ─────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        logging.info("Invite tracking cog loaded — snapshotting invites.")
        for guild in self.bot.guilds:
            await self._snapshot_guild(guild)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self._snapshot_guild(guild)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        self._snapshots.pop(guild.id, None)
        self._creators.pop(guild.id, None)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        if invite.guild is None:
            return
        gid = invite.guild.id
        self._snapshots.setdefault(gid, {})[invite.code] = invite.uses or 0
        if invite.inviter is not None:
            self._creators.setdefault(gid, {})[invite.code] = invite.inviter.id

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        if invite.guild is None:
            return
        gid = invite.guild.id
        self._snapshots.get(gid, {}).pop(invite.code, None)
        self._creators.get(gid, {}).pop(invite.code, None)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        old_snap = dict(self._snapshots.get(member.guild.id, {}))
        used_code: str | None = None
        inviter_id: int | None = None

        try:
            new_invites = await member.guild.invites()
            new_snap = {inv.code: inv.uses or 0 for inv in new_invites}

            for code, uses in new_snap.items():
                if uses > old_snap.get(code, 0):
                    used_code = code
                    break

            new_creators = {
                inv.code: inv.inviter.id
                for inv in new_invites
                if inv.inviter is not None
            }
            self._snapshots[member.guild.id] = new_snap
            self._creators[member.guild.id] = new_creators

            if used_code is not None:
                inviter_id = new_creators.get(used_code)
        except discord.Forbidden:
            pass
        except Exception:
            logging.exception(f"Failed to diff invites for guild {member.guild.id}")

        now = int(time.time())
        self._last_used[(member.guild.id, member.id)] = (used_code, now)

        # Prune stale entries — heuristics reads within a few seconds of join.
        cutoff = now - 300
        stale = [k for k, (_, ts) in self._last_used.items() if ts < cutoff]
        for key in stale:
            del self._last_used[key]

        # Post to invite log channel if configured.
        cfg = await self._guild_config(member.guild.id)
        if cfg.invite_log_channel_id:
            channel = member.guild.get_channel(cfg.invite_log_channel_id)
            if isinstance(channel, discord.TextChannel):
                await self._post_invite_log(channel, member, used_code, inviter_id, now)

    async def _post_invite_log(
        self,
        channel: discord.TextChannel,
        member: discord.Member,
        used_code: str | None,
        inviter_id: int | None,
        now: int,
    ) -> None:
        embed = discord.Embed(
            description=f"{member.mention} joined the server.",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.set_footer(text=f"Member ID: {member.id}")

        embed.add_field(
            name="Invite Code",
            value=f"`{used_code}`" if used_code else "Unknown",
            inline=True,
        )
        embed.add_field(
            name="Invited By",
            value=f"<@{inviter_id}>" if inviter_id else "Unknown",
            inline=True,
        )
        embed.add_field(
            name="Account Age",
            value=_time_ago(int(member.created_at.timestamp()), now),
            inline=True,
        )

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            logging.warning(f"Missing permissions to post invite log in {channel.id}")

    # ── Public interface for other cogs ───────────────────────────────────────

    def get_used_invite_code(self, guild_id: int, member_id: int) -> str | None:
        entry = self._last_used.get((guild_id, member_id))
        return entry[0] if entry else None

    def get_invite_creator_id(self, guild_id: int, invite_code: str) -> int | None:
        return self._creators.get(guild_id, {}).get(invite_code)

    def clear_used_invite(self, guild_id: int, member_id: int) -> None:
        self._last_used.pop((guild_id, member_id), None)

    # ── /invites commands ─────────────────────────────────────────────────────

    invites_group = app_commands.Group(
        name="invites",
        description="View and log invite usage.",
        guild_only=True,
    )

    @invites_group.command(
        name="who",
        description="See who invited a member to this server",
    )
    @app_commands.describe(member="The member to look up")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def invites_who(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        if interaction.guild is None:
            return
        await interaction.response.defer(ephemeral=True)

        track = await self.bot.database.join_tracks.get_user_track(
            interaction.guild.id, member.id
        )

        embed = discord.Embed(
            title=f"Who invited {member}?",
            color=discord.Color.blurple(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        if track is None:
            embed.description = (
                "No join record found for this member.\n"
                "Records are kept for members who joined while the heuristics engine "
                "was active, or while the invite log was configured."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        embed.add_field(
            name="Invited By",
            value=f"<@{track.inviter_id}>" if track.inviter_id else "Unknown",
            inline=True,
        )
        embed.add_field(
            name="Invite Code",
            value=f"`{track.invite_code}`" if track.invite_code else "Unknown",
            inline=True,
        )
        if track.joined_at:
            embed.add_field(
                name="Joined",
                value=f"<t:{track.joined_at}:f> (<t:{track.joined_at}:R>)",
                inline=False,
            )
        if track.score is not None:
            embed.add_field(name="Join Score", value=str(track.score), inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @invites_group.command(
        name="invitees",
        description="List everyone a member has invited to this server",
    )
    @app_commands.describe(member="The member whose invitees to list")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def invites_invitees(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        if interaction.guild is None:
            return
        await interaction.response.defer(ephemeral=True)

        tracks = await self.bot.database.join_tracks.get_invitees(
            interaction.guild.id, member.id
        )

        embed = discord.Embed(
            title=f"Members invited by {member}",
            color=discord.Color.blurple(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        if not tracks:
            embed.description = "No tracked invitees found for this member."
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        now = int(time.time())
        lines: list[str] = []
        for track in sorted(tracks, key=lambda t: t.joined_at or 0, reverse=True):
            uid = track.user_id
            if uid is None:
                continue
            joined = _time_ago(track.joined_at, now) if track.joined_at else "unknown"
            score_part = f" · score: {track.score}" if track.score is not None else ""
            lines.append(f"<@{uid}> — joined {joined}{score_part}")

        description = "\n".join(lines)
        if len(description) > 4000:
            description = description[:3990] + "\n*… (truncated)*"
        embed.description = description
        embed.set_footer(text=f"{len(tracks)} total invitee{'s' if len(tracks) != 1 else ''}")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @invites_group.command(
        name="tree",
        description="Show who a member invited, and who those people invited, recursively",
    )
    @app_commands.describe(
        member="The member to start the tree from",
        depth="How many levels deep to show (1–5, default 3)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def invites_tree(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        depth: app_commands.Range[int, 1, 5] = 3,
    ) -> None:
        if interaction.guild is None:
            return
        await interaction.response.defer(ephemeral=True)

        now = int(time.time())
        guild_id = interaction.guild.id
        MAX_NODES = 50
        lines: list[str] = []
        seen: set[int] = {member.id}
        total: list[int] = [0]

        root_track = await self.bot.database.join_tracks.get_user_track(guild_id, member.id)
        score_part = (
            f"score: {root_track.score}"
            if root_track and root_track.score is not None else "no heuristics record"
        )
        time_part = (
            f", joined {_time_ago(root_track.joined_at, now)}"
            if root_track and root_track.joined_at else ""
        )
        inviter_part = (
            f", invited by <@{root_track.inviter_id}>"
            if root_track and root_track.inviter_id else ""
        )
        lines.append(f"**{member}** ({score_part}{time_part}{inviter_part})")

        async def _recurse(user_id: int, pfx: str, d: int) -> None:
            if total[0] >= MAX_NODES:
                return
            invitees = await self.bot.database.join_tracks.get_invitees(guild_id, user_id)
            invitees = [inv for inv in invitees if inv.user_id not in seen]
            seen.update(inv.user_id for inv in invitees if inv.user_id is not None)

            remaining = MAX_NODES - total[0]
            shown, hidden = invitees[:remaining], len(invitees[remaining:])

            for i, inv in enumerate(shown):
                uid = inv.user_id
                if uid is None:
                    continue
                total[0] += 1
                is_last = (i == len(shown) - 1) and hidden == 0
                connector = "└── " if is_last else "├── "
                score = f"score: {inv.score}" if inv.score is not None else "no record"
                t = f", joined {_time_ago(inv.joined_at, now)}" if inv.joined_at else ""
                confirmed = " ✓" if inv.mod_confirmed else ""
                fp = " ✗ FP" if inv.mod_false_positive else ""
                lines.append(f"{pfx}{connector}<@{uid}> ({score}{t}{confirmed}{fp})")
                if d > 1:
                    await _recurse(uid, pfx + ("    " if is_last else "│   "), d - 1)

            if hidden > 0:
                lines.append(f"{pfx}    ⋮  ({hidden} more at this level)")

        await _recurse(member.id, "", depth)

        if len(lines) == 1:
            lines.append("*No tracked invitees found.*")

        description = "\n".join(lines)
        if len(description) > 3900:
            description = description[:3900] + "\n*… (truncated)*"

        embed = discord.Embed(
            title=f"Invite Tree: {member}",
            description=description,
            color=discord.Color.blurple(),
        )
        embed.set_footer(
            text=f"Depth {depth} • up to {MAX_NODES} nodes • ✓ = mod confirmed • ✗ FP = false positive"
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @invites_group.command(
        name="log",
        description="Set or clear the channel where new member joins are logged with invite info",
    )
    @app_commands.describe(channel="Channel to log joins to — leave blank to disable")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def invites_log(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        if interaction.guild is None:
            return

        cfg = await self._guild_config(interaction.guild.id)
        cfg.guild_id = interaction.guild.id
        cfg.invite_log_channel_id = channel.id if channel else None
        await self.bot.database.guild_config.save(cfg)

        if channel:
            await interaction.response.send_message(
                f"Invite log channel set to {channel.mention}. "
                "Every new member join will be posted there with invite code and inviter info.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "Invite log disabled.", ephemeral=True
            )


async def setup(bot: KidneyBot) -> None:
    await bot.add_cog(InviteTracking(bot))
