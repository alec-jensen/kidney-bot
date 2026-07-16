# Moderation commands and action infrastructure.
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Literal
from uuid import uuid4

import discord
import humanize
from discord import app_commands
from discord.ext import commands

from cogs.moderation_views import ACTION_COLORS, ACTION_LABELS, ActionInsightView, ModerationHistoryView
from utils.database import Schemas
from utils.kidney_bot import KidneyBot
from utils.misc import ordinal
from utils.mod_insight import DEFAULT_RULES, EscalationRule, InsightResult, analyze
from utils.types import AnyUser

time_convert = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
}

class Moderation(commands.Cog):
    def __init__(self, bot: KidneyBot):
        self.bot: KidneyBot = bot

    # ── Listeners ─────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        logging.info("Moderation cog loaded.")

    # ── Internal helpers ───────────────────────────────────────────────────────

    async def permissionHierarchyCheck(self, user: discord.Member, target: discord.Member) -> bool | None:
        logging.debug(f"Checking permission hierarchy for {user} and {target}.")
        if target.top_role >= user.top_role:
            return True if user.guild.owner == user else False
        return True

    async def convert_time_to_seconds(self, time_str: str) -> int | bool:
        times: list[str] = []
        current = ""
        for char in time_str:
            current += char
            if char.isalpha():
                times.append(current)
                current = ""
        if current:
            return False
        seconds = 0
        for part in times:
            if part[-1] not in time_convert:
                return False
            seconds += int(part[:-1]) * time_convert[part[-1]]
        return seconds

    async def get_ephemeral_messages(
        self,
        guild: discord.Guild | None = None,
        user: discord.User | discord.Member | None = None,
    ) -> bool:
        if guild is None and user is None:
            raise ValueError("guild and user cannot both be None")
        if guild is not None:
            doc = await self.bot.database.guild_config.get(guild.id)
            if doc is not None:
                if doc.ephemeral_setting_overpowers_user_setting or user is None:
                    return bool(doc.ephemeral_moderation_messages)
        if user is not None:
            doc2 = await self.bot.database.user_config.get(user.id)
            if doc2 is not None:
                return bool(doc2.ephemeral_moderation_messages)
        return True

    async def _require_reason_if_configured(
        self,
        interaction: discord.Interaction,
        guild: discord.Guild,
        reason: str | None,
    ) -> bool:
        """Return True (and send an ephemeral rejection) if this guild requires a
        reason and none was provided — callers should abort the command in that case."""
        if reason:
            return False
        config = await self.bot.database.mod_config.get(guild.id)
        if config is not None and config.require_reason:
            await interaction.followup.send(
                "This server requires a reason for moderation actions.", ephemeral=True)
            return True
        return False

    async def _record_action(
        self,
        action_type: str,
        user: discord.Member | None,
        guild: discord.Guild,
        moderator: discord.Member,
        reason: str | None = None,
        duration: int | None = None,
    ) -> Schemas.ModLogEntry:
        now = int(time.time())
        entry = Schemas.ModLogEntry(
            id=str(uuid4()),
            guild_id=guild.id,
            user_id=user.id if user is not None else None,
            moderator_id=moderator.id,
            action_type=action_type,
            reason=reason,
            timestamp=now,
            duration=duration,
            expires_at=(now + duration) if duration else None,
        )
        await self.bot.database.mod_log.save(entry)
        self.bot.dispatch('modlog_entry', entry, guild)
        return entry

    async def _get_insight(
        self,
        user: discord.Member,
        guild: discord.Guild,
    ) -> InsightResult:
        history = await self.bot.database.mod_log.get_user_history(user.id, guild.id)
        config = await self.bot.database.mod_config.get(guild.id)
        guild_rules = config.escalation_rules if config else None
        return analyze(history, guild_rules)

    async def _send_insight(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        insight: InsightResult,
    ) -> None:
        if not insight.has_notable_history:
            return
        embed = discord.Embed(
            title=f"Moderation Insight: {user.display_name}",
            color=discord.Color.orange(),
        )
        embed.add_field(name="Recent Activity", value=insight.summary.describe(), inline=False)
        if insight.matched_rule:
            rule = insight.matched_rule
            embed.add_field(
                name="⚠️ Escalation Threshold Reached",
                value=(
                    f"{rule.min_count}+ {'/'.join(rule.action_types)} "
                    f"in {rule.window_days} day{'s' if rule.window_days != 1 else ''}"
                ),
                inline=False,
            )
        view = ActionInsightView(self, user, insight.suggestions)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def _post_to_log_channel(
        self,
        guild: discord.Guild,
        entry: Schemas.ModLogEntry,
        insight: InsightResult,
        moderator: AnyUser,
        user: AnyUser,
    ) -> None:
        config = await self.bot.database.mod_config.get(guild.id)
        if not config or not config.log_channel_id:
            return
        channel = guild.get_channel(config.log_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        label = ACTION_LABELS.get(entry.action_type or "", (entry.action_type or "").upper())
        embed = discord.Embed(
            title=f"{label} — {user}",
            color=ACTION_COLORS.get(entry.action_type or "", discord.Color.blurple()),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="User", value=f"{user.mention} ({user.id})", inline=True)
        embed.add_field(name="Moderator", value=moderator.mention, inline=True)
        if entry.reason:
            embed.add_field(name="Reason", value=entry.reason, inline=False)
        if entry.duration:
            embed.add_field(
                name="Duration",
                value=humanize.precisedelta(timedelta(seconds=entry.duration), format="%0.0f"),
                inline=True,
            )
        history_desc = insight.summary.describe()
        if history_desc != "no actions in the last 7 days":
            embed.add_field(name="User's Recent History", value=history_desc, inline=False)
        embed.set_footer(text=f"Action ID: {entry.id}")

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            logging.warning(
                f"Cannot post to mod log channel {config.log_channel_id} in guild {guild.id}"
            )

    # ── Action executors (shared by slash commands and quick-action buttons) ───

    async def _execute_warn(
        self,
        user: discord.Member,
        moderator: discord.Member,
        guild: discord.Guild,
        reason: str,
    ) -> Schemas.ModLogEntry:
        return await self._record_action("warn", user, guild, moderator, reason)

    async def _execute_mute(
        self,
        user: discord.Member,
        moderator: discord.Member,
        guild: discord.Guild,
        reason: str | None,
    ) -> Schemas.ModLogEntry:
        role = discord.utils.get(guild.roles, name="Muted")
        if role is None:
            raise ValueError('Muted role not found. Please create a "Muted" role.')
        await user.add_roles(role, reason=f"by {moderator} for {reason}")
        return await self._record_action("mute", user, guild, moderator, reason)

    async def _execute_unmute(
        self,
        user: discord.Member,
        moderator: discord.Member,
        guild: discord.Guild,
    ) -> Schemas.ModLogEntry:
        await user.edit(timed_out_until=None)
        role = discord.utils.get(guild.roles, name="Muted")
        if role is not None and role in user.roles:
            await user.remove_roles(role)
        return await self._record_action("unmute", user, guild, moderator)

    async def _execute_tempmute(
        self,
        user: discord.Member,
        moderator: discord.Member,
        guild: discord.Guild,
        time_str: str,
        reason: str | None,
    ) -> Schemas.ModLogEntry:
        seconds = await self.convert_time_to_seconds(time_str)
        if seconds is False:
            raise ValueError(f"Invalid time format: {time_str!r}")
        if seconds > 1209600:
            raise ValueError("Timeouts can only be 2 weeks max.")
        until = timedelta(seconds=seconds)
        await user.timeout(until, reason=reason)
        try:
            await user.send(
                f"You have been timed out in **{guild}** for "
                f"*{humanize.precisedelta(until, format='%0.0f')}*"
            )
        except discord.Forbidden:
            pass
        return await self._record_action("tempmute", user, guild, moderator, reason, int(seconds))

    async def _execute_kick(
        self,
        user: discord.Member,
        moderator: discord.Member,
        guild: discord.Guild,
        reason: str | None,
    ) -> Schemas.ModLogEntry:
        await guild.kick(user, reason=reason)
        return await self._record_action("kick", user, guild, moderator, reason)

    async def _execute_ban(
        self,
        user: discord.Member,
        moderator: discord.Member,
        guild: discord.Guild,
        reason: str | None,
        delete_message_seconds: int = 0,
    ) -> Schemas.ModLogEntry:
        await guild.ban(user, reason=reason, delete_message_seconds=delete_message_seconds)
        return await self._record_action("ban", user, guild, moderator, reason)

    # ── Ephemeral-messages config ──────────────────────────────────────────────

    ephemeral_messages = app_commands.Group(
        name="ephemeral_messages",
        description="Configure whether moderation messages are ephemeral",
    )

    @ephemeral_messages.command(name="guild", description="Configure ephemeral moderation messages for the guild")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def ephemeral_messages_guild(
        self, interaction: discord.Interaction, ephemeral: Literal["Yes", "No"]
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        doc = await self.bot.database.guild_config.get(interaction.guild.id) or \
              Schemas.GuildConfig(guild_id=interaction.guild.id)
        doc.ephemeral_moderation_messages = ephemeral == "Yes"
        await self.bot.database.guild_config.save(doc)
        await interaction.followup.send(f"Moderation messages are now ephemeral: {ephemeral}", ephemeral=True)

    @ephemeral_messages.command(name="force_guild_setting", description="Force guild ephemeral setting over user setting")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def ephemeral_messages_force_guild_setting(
        self, interaction: discord.Interaction, force: Literal["Yes", "No"]
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        doc = await self.bot.database.guild_config.get(interaction.guild.id) or \
              Schemas.GuildConfig(guild_id=interaction.guild.id)
        doc.ephemeral_setting_overpowers_user_setting = force == "Yes"
        await self.bot.database.guild_config.save(doc)
        await interaction.followup.send(f"Guild setting overpowers user setting: {force}", ephemeral=True)

    @ephemeral_messages.command(name="self", description="Configure ephemeral moderation messages for yourself")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def ephemeral_messages_user(
        self, interaction: discord.Interaction, ephemeral: Literal["Yes", "No"]
    ) -> None:
        import asyncio
        await interaction.response.defer(ephemeral=True)
        doc_task = asyncio.create_task(self.bot.database.guild_config.get(interaction.guild.id))  # type: ignore[arg-type]
        user_doc = await self.bot.database.user_config.get(interaction.user.id) or \
                   Schemas.UserConfig(user_id=interaction.user.id)
        user_doc.ephemeral_moderation_messages = ephemeral == "Yes"
        await self.bot.database.user_config.save(user_doc)
        doc = await doc_task
        if doc is not None and doc.ephemeral_setting_overpowers_user_setting:
            forced = "ephemeral" if doc.ephemeral_moderation_messages else "not ephemeral"
            await interaction.followup.send(
                f"Moderation messages are now ephemeral: {ephemeral}\n"
                f"*(Due to this guild's settings, all messages are forced to be {forced})*",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(f"Moderation messages are now ephemeral: {ephemeral}", ephemeral=True)

    # ── Moderation config ──────────────────────────────────────────────────────

    modconfig = app_commands.Group(
        name="modconfig",
        description="Configure moderation system settings",
        guild_only=True,
    )

    @modconfig.command(name="log_channel", description="Set or clear the moderation log channel")
    @app_commands.default_permissions(administrator=True)
    async def modconfig_log_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        doc = await self.bot.database.mod_config.get(interaction.guild.id) or \
              Schemas.ModConfig(guild_id=interaction.guild.id)
        doc.log_channel_id = channel.id if channel else None
        await self.bot.database.mod_config.save(doc)
        if channel:
            await interaction.followup.send(f"Mod log channel set to {channel.mention}.", ephemeral=True)
        else:
            await interaction.followup.send("Mod log channel cleared.", ephemeral=True)

    @modconfig.command(name="require_reason", description="Require a reason for moderation actions")
    @app_commands.default_permissions(manage_guild=True)
    async def modconfig_require_reason(
        self,
        interaction: discord.Interaction,
        require: Literal["Yes", "No"],
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        doc = await self.bot.database.mod_config.get(interaction.guild.id) or \
              Schemas.ModConfig(guild_id=interaction.guild.id)
        doc.require_reason = require == "Yes"
        await self.bot.database.mod_config.save(doc)
        await interaction.followup.send(f"Require reason for moderation actions: {require}", ephemeral=True)

    @modconfig.command(name="escalation_view", description="View current escalation rules")
    @app_commands.default_permissions(administrator=True)
    async def modconfig_escalation_view(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        doc = await self.bot.database.mod_config.get(interaction.guild.id)
        if doc and doc.escalation_rules:
            rules = [EscalationRule.from_dict(r) for r in doc.escalation_rules]
            title = "Custom Escalation Rules"
        else:
            rules = DEFAULT_RULES
            title = "Default Escalation Rules"
        embed = discord.Embed(title=title, color=discord.Color.blurple())
        for rule in rules:
            suggestions_str = ", ".join(s.label() for s in rule.suggestions)
            embed.add_field(
                name=f"{rule.min_count}+ {'/'.join(rule.action_types)} in {rule.window_days}d",
                value=f"Suggest: {suggestions_str}",
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @modconfig.command(name="escalation_reset", description="Reset escalation rules to defaults")
    @app_commands.default_permissions(administrator=True)
    async def modconfig_escalation_reset(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        doc = await self.bot.database.mod_config.get(interaction.guild.id) or \
              Schemas.ModConfig(guild_id=interaction.guild.id)
        doc.escalation_rules = None
        await self.bot.database.mod_config.save(doc)
        await interaction.followup.send("Escalation rules reset to defaults.", ephemeral=True)

    # ── Moderation commands ────────────────────────────────────────────────────

    @app_commands.command(name="nickname", description="Change a user's nickname")
    @app_commands.default_permissions(manage_nicknames=True)
    @app_commands.guild_only()
    @app_commands.describe(user="The user to change the nickname of", newnick="The new nickname — leave blank to reset")
    async def nickname(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        *,
        newnick: str | None = None,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This command requires server member context.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=await self.get_ephemeral_messages(interaction.guild, interaction.user))
        if not await self.permissionHierarchyCheck(interaction.user, user):
            await interaction.followup.send("You cannot moderate users higher than you.", ephemeral=True)
            return
        old_nick = user.display_name
        try:
            await user.edit(nick=newnick)
        except discord.Forbidden:
            await interaction.followup.send("Missing required permissions. Is the user above me?", ephemeral=True)
            return
        reason = f"Nickname changed from {old_nick!r} to {(newnick or '(reset)')!r}"
        entry = await self._record_action("nickname", user, interaction.guild, interaction.user, reason)
        embed = discord.Embed(title="Nickname changed", color=discord.Color.green())
        embed.add_field(name="User", value=user.mention, inline=False)
        embed.add_field(name="Old nickname", value=old_nick, inline=False)
        embed.add_field(name="New nickname", value=newnick or "*(reset)*", inline=False)
        embed.set_footer(text=f"Moderator: {interaction.user} • Action ID: {entry.id}")
        await interaction.followup.send(embed=embed, ephemeral=await self.get_ephemeral_messages(interaction.guild))

    @app_commands.command(name="purge", description="Purge messages")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def purge(
        self,
        interaction: discord.Interaction,
        limit: int,
        user: discord.Member | None = None,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This command requires server member context.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=await self.get_ephemeral_messages(interaction.guild))
        purged = 0
        if interaction.channel and isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
            if user is None:
                deleted = await interaction.channel.purge(limit=limit, before=interaction.created_at)
                purged = len(deleted)
            else:
                msg: list[discord.Message] = []
                async for m in interaction.channel.history():
                    if len(msg) == limit:
                        break
                    if m.author == user:
                        msg.append(m)
                if hasattr(interaction.channel, "delete_messages"):
                    await interaction.channel.delete_messages(msg)
                purged = len(msg)
        reason = f"Purged {purged} message(s) in #{interaction.channel}" + \
                 (f" from {user}" if user else "")
        entry = await self._record_action("purge", user, interaction.guild, interaction.user, reason)
        embed = discord.Embed(title="Purge result", color=discord.Color.green())
        embed.add_field(name="Messages purged", value=purged, inline=False)
        embed.set_footer(text=f"Moderator: {interaction.user} • Action ID: {entry.id}", icon_url=interaction.user.avatar)
        await interaction.followup.send(embed=embed, ephemeral=await self.get_ephemeral_messages(interaction.guild))

    @app_commands.command(name="warn", description="Warn a user")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def warn(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        *,
        reason: str,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This command requires server member context.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=await self.get_ephemeral_messages(interaction.guild, interaction.user))
        if not await self.permissionHierarchyCheck(interaction.user, user):
            await interaction.followup.send("You cannot moderate users higher than you.", ephemeral=True)
            return

        entry = await self._execute_warn(user, interaction.user, interaction.guild, reason)
        insight = await self._get_insight(user, interaction.guild)
        total_warns = insight.summary.count_all("warn")

        dm_embed = discord.Embed(
            title=f"You have been warned in {interaction.guild}", color=discord.Color.red())
        dm_embed.add_field(name="Reason", value=reason, inline=False)
        dm_embed.add_field(name="Action ID", value=entry.id, inline=False)
        dm_embed.set_footer(text=f"This is your {ordinal(total_warns)} warning")
        failed_dms = False
        try:
            await user.send(embed=dm_embed)
        except discord.Forbidden:
            failed_dms = True

        embed = discord.Embed(title="Warn result", color=discord.Color.red())
        embed.add_field(name="Warned", value=user.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=True)
        embed.add_field(
            name="History",
            value=f"This is their {ordinal(total_warns)} warning\n{insight.summary.describe()}",
            inline=False,
        )
        if failed_dms:
            embed.add_field(name="Note", value="Could not DM user (DMs disabled)", inline=False)
        embed.set_footer(text=f"Moderator: {interaction.user} • Action ID: {entry.id}")
        await interaction.followup.send(
            embed=embed, ephemeral=await self.get_ephemeral_messages(interaction.guild))
        await self._post_to_log_channel(interaction.guild, entry, insight, interaction.user, user)
        await self._send_insight(interaction, user, insight)

    @app_commands.command(name="mute", description="Mute a user (role-based)")
    @app_commands.default_permissions(mute_members=True)
    @app_commands.guild_only()
    async def mute(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        *,
        reason: str | None = None,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This command requires server member context.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=await self.get_ephemeral_messages(interaction.guild, interaction.user))
        if not await self.permissionHierarchyCheck(interaction.user, user):
            await interaction.followup.send("You cannot moderate users higher than you.", ephemeral=True)
            return
        if await self._require_reason_if_configured(interaction, interaction.guild, reason):
            return
        try:
            entry = await self._execute_mute(user, interaction.user, interaction.guild, reason)
        except ValueError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return

        insight = await self._get_insight(user, interaction.guild)
        embed = discord.Embed(title="Mute result", color=discord.Color.red())
        embed.add_field(name="Muted", value=user.mention, inline=True)
        embed.add_field(name="Reason", value=reason or "No reason provided", inline=True)
        embed.add_field(name="History", value=insight.summary.describe(), inline=False)
        embed.set_footer(text=f"Moderator: {interaction.user} • Action ID: {entry.id}")
        await interaction.followup.send(
            embed=embed, ephemeral=await self.get_ephemeral_messages(interaction.guild))
        await self._post_to_log_channel(interaction.guild, entry, insight, interaction.user, user)
        await self._send_insight(interaction, user, insight)

    @app_commands.command(name="unmute", description="Unmute a user")
    @app_commands.default_permissions(mute_members=True)
    @app_commands.guild_only()
    async def unmute(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This command requires server member context.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=await self.get_ephemeral_messages(interaction.guild, interaction.user))
        if not await self.permissionHierarchyCheck(interaction.user, user):
            await interaction.followup.send("You cannot moderate users higher than you.", ephemeral=True)
            return

        entry = await self._execute_unmute(user, interaction.user, interaction.guild)
        embed = discord.Embed(title="Unmute result", color=discord.Color.green())
        embed.add_field(name="Unmuted", value=user.mention, inline=False)
        embed.set_footer(text=f"Moderator: {interaction.user} • Action ID: {entry.id}")
        await interaction.followup.send(
            embed=embed, ephemeral=await self.get_ephemeral_messages(interaction.guild))

    @app_commands.command(name="tempmute", description="Timeout a user for a set duration")
    @app_commands.default_permissions(mute_members=True)
    @app_commands.guild_only()
    async def tempmute(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        time: str,
        *,
        reason: str | None = None,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This command requires server member context.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=await self.get_ephemeral_messages(interaction.guild, interaction.user))
        if not await self.permissionHierarchyCheck(interaction.user, user):
            await interaction.followup.send("You cannot moderate users higher than you.", ephemeral=True)
            return
        if await self._require_reason_if_configured(interaction, interaction.guild, reason):
            return
        try:
            entry = await self._execute_tempmute(user, interaction.user, interaction.guild, time, reason)
        except ValueError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return

        insight = await self._get_insight(user, interaction.guild)
        duration_str = humanize.precisedelta(
            timedelta(seconds=entry.duration or 0), format="%0.0f")
        embed = discord.Embed(title="Timeout result", color=discord.Color.red())
        embed.add_field(name="Timed out", value=user.mention, inline=True)
        embed.add_field(name="Duration", value=duration_str, inline=True)
        embed.add_field(name="Reason", value=reason or "No reason provided", inline=True)
        embed.add_field(name="History", value=insight.summary.describe(), inline=False)
        embed.set_footer(text=f"Moderator: {interaction.user} • Action ID: {entry.id}")
        await interaction.followup.send(
            embed=embed, ephemeral=await self.get_ephemeral_messages(interaction.guild))
        await self._post_to_log_channel(interaction.guild, entry, insight, interaction.user, user)
        await self._send_insight(interaction, user, insight)

    @app_commands.command(name="kick", description="Kick users")
    @app_commands.describe(users="Users to kick, comma-separated", delete_message_time="Time window to delete messages from")
    @app_commands.default_permissions(kick_members=True)
    @app_commands.guild_only()
    async def kick(
        self,
        interaction: discord.Interaction,
        users: str,
        reason: str | None = None,
        delete_message_time: str | None = None,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This command requires server member context.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=await self.get_ephemeral_messages(interaction.guild, interaction.user))
        if await self._require_reason_if_configured(interaction, interaction.guild, reason):
            return

        max_delete_time = 0
        if delete_message_time is not None:
            result = await self.convert_time_to_seconds(delete_message_time)
            if result is False:
                await interaction.followup.send("Invalid delete message time.", ephemeral=True)
                return
            max_delete_time = int(result)

        converter = commands.MemberConverter()
        ctx = await commands.Context.from_interaction(interaction)
        kicked: list[discord.Member] = []

        for user_str in [u.strip() for u in users.split(",")]:
            try:
                user = await converter.convert(ctx, user_str)
                if not await self.permissionHierarchyCheck(interaction.user, user):
                    await interaction.followup.send("You cannot moderate users higher than you.", ephemeral=True)
                    return
                entry = await self._execute_kick(user, interaction.user, interaction.guild, reason)
                kicked.append(user)
                insight = await self._get_insight(user, interaction.guild)
                await self._post_to_log_channel(interaction.guild, entry, insight, interaction.user, user)
            except Exception as e:
                await interaction.followup.send(f"Failed to kick {user_str}: {e}", ephemeral=True)
                return

        if max_delete_time > 0:
            for channel in interaction.guild.channels:
                if isinstance(channel, (discord.TextChannel, discord.Thread)):
                    try:
                        async for message in channel.history():
                            if message.author in kicked:
                                if message.created_at > interaction.created_at - timedelta(seconds=max_delete_time):
                                    await message.delete()
                    except Exception:
                        pass

        embed = discord.Embed(title="Kick result", color=discord.Color.red())
        embed.add_field(name="Kicked", value=", ".join(u.mention for u in kicked), inline=False)
        embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
        embed.set_footer(text=f"Moderator: {interaction.user}", icon_url=interaction.user.avatar)
        await interaction.followup.send(
            embed=embed, ephemeral=await self.get_ephemeral_messages(interaction.guild))

        if len(kicked) == 1:
            insight = await self._get_insight(kicked[0], interaction.guild)
            await self._send_insight(interaction, kicked[0], insight)

    @app_commands.command(name="ban", description="Ban users")
    @app_commands.describe(users="Users to ban, comma-separated", delete_message_time="Time window to delete messages from (max 7 days)")
    @app_commands.default_permissions(ban_members=True)
    @app_commands.guild_only()
    async def ban(
        self,
        interaction: discord.Interaction,
        users: str,
        reason: str | None = None,
        delete_message_time: str | None = None,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This command requires server member context.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=await self.get_ephemeral_messages(interaction.guild, interaction.user))
        if await self._require_reason_if_configured(interaction, interaction.guild, reason):
            return

        delete_message_seconds = 0
        if delete_message_time is not None:
            result = await self.convert_time_to_seconds(delete_message_time)
            if result is False:
                await interaction.followup.send("Invalid delete message time.", ephemeral=True)
                return
            delete_message_seconds = int(result)
        if delete_message_seconds > 604800:
            await interaction.followup.send("Can only delete messages up to 7 days old.", ephemeral=True)
            return

        converter = commands.MemberConverter()
        ctx = await commands.Context.from_interaction(interaction)
        banned: list[discord.Member] = []

        for user_str in [u.strip() for u in users.split(",")]:
            try:
                user = await converter.convert(ctx, user_str)
                if not await self.permissionHierarchyCheck(interaction.user, user):
                    await interaction.followup.send("You cannot moderate users higher than you.", ephemeral=True)
                    return
                entry = await self._execute_ban(user, interaction.user, interaction.guild, reason, delete_message_seconds)
                banned.append(user)
                insight = await self._get_insight(user, interaction.guild)
                await self._post_to_log_channel(interaction.guild, entry, insight, interaction.user, user)
            except Exception as e:
                await interaction.followup.send(f"Failed to ban {user_str}: {e}", ephemeral=True)
                return

        embed = discord.Embed(title="Ban result", color=discord.Color.dark_red())
        embed.add_field(name="Banned", value=", ".join(u.mention for u in banned), inline=False)
        embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
        embed.set_footer(text=f"Moderator: {interaction.user}", icon_url=interaction.user.avatar)
        await interaction.followup.send(
            embed=embed, ephemeral=await self.get_ephemeral_messages(interaction.guild))

        if len(banned) == 1:
            insight = await self._get_insight(banned[0], interaction.guild)
            await self._send_insight(interaction, banned[0], insight)

    @app_commands.command(name="unban", description="Unban users")
    @app_commands.describe(users="Users to unban, comma-separated")
    @app_commands.default_permissions(ban_members=True)
    @app_commands.guild_only()
    async def unban(
        self,
        interaction: discord.Interaction,
        users: str,
        reason: str | None = None,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This command requires server member context.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=await self.get_ephemeral_messages(interaction.guild))

        converter = commands.MemberConverter()
        ctx = await commands.Context.from_interaction(interaction)
        unbanned: list[discord.Member] = []

        for user_str in [u.strip() for u in users.split(",")]:
            try:
                user = await converter.convert(ctx, user_str)
                await interaction.guild.unban(user, reason=reason)
                unbanned.append(user)
                await self._record_action("unban", user, interaction.guild, interaction.user, reason)
            except Exception:
                await interaction.followup.send(f"User {user_str} not found.", ephemeral=True)
                return

        embed = discord.Embed(title="Unban result", color=discord.Color.green())
        embed.add_field(name="Unbanned", value=", ".join(u.mention for u in unbanned), inline=False)
        embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
        embed.set_footer(text=f"Moderator: {interaction.user}", icon_url=interaction.user.avatar)
        await interaction.followup.send(
            embed=embed, ephemeral=await self.get_ephemeral_messages(interaction.guild))

    # ── History and audit commands ─────────────────────────────────────────────

    @app_commands.command(name="history", description="View moderation history for a user")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def history(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        await interaction.response.defer()
        view = ModerationHistoryView(self.bot, user, interaction.guild)
        await view.async_init()
        embed = view._build_embed()
        await interaction.followup.send(embed=embed, view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="actioninfo", description="Get information about a moderation action by ID")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def actioninfo(
        self,
        interaction: discord.Interaction,
        action_id: str,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=await self.get_ephemeral_messages(interaction.guild))
        entry = await self.bot.database.mod_log.get(action_id)
        if entry is None or entry.guild_id != interaction.guild.id:
            await interaction.followup.send("Action not found.", ephemeral=True)
            return

        user = await self.bot.fetch_user(entry.user_id) if entry.user_id else None
        moderator = await self.bot.fetch_user(entry.moderator_id) if entry.moderator_id else None

        label = ACTION_LABELS.get(entry.action_type or "", entry.action_type or "Action")
        embed = discord.Embed(title=f"Action Info — {label}", color=discord.Color.red())
        embed.add_field(name="User", value=user.mention if user else str(entry.user_id), inline=True)
        embed.add_field(name="Moderator", value=moderator.mention if moderator else str(entry.moderator_id), inline=True)
        embed.add_field(name="Reason", value=entry.reason or "No reason provided", inline=False)
        embed.add_field(name="Timestamp", value=f"<t:{entry.timestamp}:F>", inline=True)
        if entry.duration:
            embed.add_field(
                name="Duration",
                value=humanize.precisedelta(timedelta(seconds=entry.duration), format="%0.0f"),
                inline=True,
            )
        embed.set_footer(text=f"Action ID: {entry.id}")
        await interaction.followup.send(
            embed=embed, ephemeral=await self.get_ephemeral_messages(interaction.guild))

    @app_commands.command(name="clearhistory", description="Clear all moderation history for a user")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def clearhistory(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This command requires server member context.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=await self.get_ephemeral_messages(interaction.guild, interaction.user))
        if not await self.permissionHierarchyCheck(interaction.user, user):
            await interaction.followup.send("You cannot moderate users higher than you.", ephemeral=True)
            return
        deleted = await self.bot.database.mod_log.delete_user_history(user.id, interaction.guild.id)
        await interaction.followup.send(
            f"Cleared {deleted} action(s) from {user.mention}'s history.",
            ephemeral=await self.get_ephemeral_messages(interaction.guild),
        )

    @app_commands.command(name="removeaction", description="Remove a specific action from a user's history")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def removeaction(
        self,
        interaction: discord.Interaction,
        action_id: str,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This command requires server member context.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=await self.get_ephemeral_messages(interaction.guild, interaction.user))
        entry = await self.bot.database.mod_log.get(action_id)
        if entry is None or entry.guild_id != interaction.guild.id:
            await interaction.followup.send("Action not found.", ephemeral=True)
            return
        target = interaction.guild.get_member(entry.user_id) if entry.user_id else None
        if target and not await self.permissionHierarchyCheck(interaction.user, target):
            await interaction.followup.send("You cannot modify actions for users higher than you.", ephemeral=True)
            return
        await self.bot.database.mod_log.delete(action_id)
        await interaction.followup.send(
            f"Action `{action_id}` removed.",
            ephemeral=await self.get_ephemeral_messages(interaction.guild),
        )


async def setup(bot: KidneyBot) -> None:
    await bot.add_cog(Moderation(bot))
