# Honeypot channel — catches bots that send messages before verifying.
# A persistent button lets humans verify; any message triggers a configured action.
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

from __future__ import annotations

import logging
import time
from datetime import timedelta
from uuid import uuid4

import discord
from discord import app_commands
from discord.ext import commands

from utils.database import Schemas
from utils.kidney_bot import KidneyBot

# ── Persistent verify button ──────────────────────────────────────────────────

class HoneypotVerifyView(discord.ui.View):
    """Persistent view (timeout=None) — survives bot restarts via custom_id routing.

    Only one instance needs to be registered with bot.add_view(); interaction.guild_id
    identifies which server the click came from so we can look up per-guild config.
    """

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="I'm a real person",
        style=discord.ButtonStyle.green,
        custom_id="honeypot:verify",
        emoji="✅",
    )
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Verification only works inside a server.", ephemeral=True)
            return

        bot: KidneyBot = interaction.client  # type: ignore[assignment]
        cfg = await bot.database.honeypot_config.get(interaction.guild.id)
        if cfg is None or not cfg.enabled or not cfg.channel_id:
            await interaction.response.send_message(
                "Honeypot is not configured for this server.", ephemeral=True)
            return

        member = interaction.user
        did_something = False

        # Lockdown mode: member has a pending role that blocks everything
        if cfg.pending_role_id:
            pending_role = interaction.guild.get_role(cfg.pending_role_id)
            if pending_role and pending_role in member.roles:
                try:
                    await member.remove_roles(pending_role, reason="Honeypot: verified")
                    did_something = True
                except discord.Forbidden:
                    await interaction.response.send_message(
                        "I couldn't verify you — please contact a moderator.", ephemeral=True)
                    return

        # Visibility mode: add verified role which hides the honeypot channel
        if cfg.verify_role_id:
            verify_role = interaction.guild.get_role(cfg.verify_role_id)
            if verify_role and verify_role not in member.roles:
                try:
                    await member.add_roles(verify_role, reason="Honeypot: verified")
                    did_something = True
                except discord.Forbidden:
                    await interaction.response.send_message(
                        "I couldn't verify you — please contact a moderator.", ephemeral=True)
                    return

        if did_something:
            await interaction.response.send_message(
                "✅ You've been verified! You now have access to the server.", ephemeral=True)
        else:
            await interaction.response.send_message(
                "You're already verified!", ephemeral=True)


# ── Verification embed (constant) ─────────────────────────────────────────────

_VERIFY_EMBED = discord.Embed(
    title="⚠️  Verification Required",
    description=(
        "Welcome! To access this server you must verify that you're a real person.\n\n"
        "**Click the button below to gain access.**\n\n"
        "⛔ **Warning:** Sending any message in this channel will be treated as automated "
        "bot activity and will result in immediate action (mute, kick, or ban). "
        "This channel is an automated honeypot."
    ),
    color=discord.Color.orange(),
)
_VERIFY_EMBED.set_footer(text="Automated verification • kidney bot")


# ── Cog ───────────────────────────────────────────────────────────────────────

class Honeypot(commands.Cog):
    def __init__(self, bot: KidneyBot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        # One registration covers all guilds — the custom_id is global.
        self.bot.add_view(HoneypotVerifyView())
        logging.info("Honeypot cog loaded — persistent verify view registered.")

    # ── Listeners ─────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return
        cfg = await self.bot.database.honeypot_config.get(member.guild.id)
        if cfg is None or not cfg.enabled or not cfg.channel_id:
            return

        # Lockdown mode: add the pending role so the member can only see the honeypot channel
        if cfg.mode == "lockdown" and cfg.pending_role_id:
            role = member.guild.get_role(cfg.pending_role_id)
            if role:
                try:
                    await member.add_roles(role, reason="Honeypot: pending verification")
                except discord.Forbidden:
                    logging.warning(
                        f"Honeypot: can't add pending role to {member} in {member.guild}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        if not isinstance(message.author, discord.Member):
            return

        cfg = await self.bot.database.honeypot_config.get(message.guild.id)
        if cfg is None or not cfg.enabled or not cfg.channel_id:
            return
        if message.channel.id != cfg.channel_id:
            return

        member = message.author
        action = cfg.message_action or "kick"
        reason = "Sent a message in the honeypot verification channel (automated bot detection)"
        now = int(time.time())

        # Delete the message before anyone sees it
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        # Record a modlog entry
        entry = Schemas.ModLogEntry(
            id=str(uuid4()),
            guild_id=message.guild.id,
            user_id=member.id,
            moderator_id=message.guild.me.id,
            action_type=action,
            reason=reason,
            timestamp=now,
        )
        await self.bot.database.mod_log.save(entry)
        # Inform network cog so it can propagate and log to tamper-proof server
        self.bot.dispatch('modlog_entry', entry, message.guild)
        self.bot.dispatch('honeypot_trigger', message.guild, member, action, message.content)

        # Alert mods
        if cfg.alert_channel_id:
            alert_ch = message.guild.get_channel(cfg.alert_channel_id)
            if isinstance(alert_ch, discord.TextChannel):
                embed = discord.Embed(
                    title="Honeypot Triggered",
                    description=(
                        f"{member.mention} (`{member.id}`) sent a message in the "
                        f"honeypot channel.\n**Content:** "
                        f"{message.content[:500] or '*(no text)*'}"
                    ),
                    color=discord.Color.red(),
                )
                embed.add_field(name="Action Taken", value=action.title(), inline=True)
                embed.add_field(
                    name="Account Age",
                    value=f"<t:{int(member.created_at.timestamp())}:R>",
                    inline=True,
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                try:
                    await alert_ch.send(embed=embed)
                except discord.Forbidden:
                    pass

        # Execute the action
        try:
            if action == "ban":
                await member.ban(reason=reason, delete_message_days=0)
            elif action == "kick":
                await member.kick(reason=reason)
            elif action == "mute":
                await member.timeout(timedelta(hours=24), reason=reason)
        except discord.Forbidden:
            logging.warning(
                f"Honeypot: no permission to {action} {member} in {message.guild}")

    # ── Commands ──────────────────────────────────────────────────────────────

    honeypot_group = app_commands.Group(
        name="honeypot",
        description="Configure the honeypot verification channel",
    )

    @honeypot_group.command(
        name="enable",
        description="Enable the honeypot in a channel and post the verification message")
    @app_commands.describe(
        channel="The channel to use as the honeypot",
        mode=(
            "lockdown: assign a pending role on join; "
            "visibility: hide channel once verified (default)"
        ),
        action="What happens when someone sends a message here",
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="visibility (hide channel on verify)", value="visibility"),
            app_commands.Choice(name="lockdown (pending role on join)", value="lockdown"),
        ],
        action=[
            app_commands.Choice(name="kick (default)", value="kick"),
            app_commands.Choice(name="ban", value="ban"),
            app_commands.Choice(name="mute 24h", value="mute"),
        ],
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def honeypot_enable(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        mode: str = "visibility",
        action: str = "kick",
    ) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)

        cfg = await self.bot.database.honeypot_config.get(interaction.guild.id)
        if cfg is None:
            cfg = Schemas.HoneypotConfig(guild_id=interaction.guild.id)

        # Clean up the previous verify message, if any — the old channel may differ
        # from the new one, so resolve it from the pre-update cfg.
        # NOTE: the API-side enable endpoint (services/api/app/routers/honeypot.py)
        # needs the same cleanup; that's tracked separately.
        if cfg.message_id and cfg.channel_id:
            old_channel = interaction.guild.get_channel(cfg.channel_id)
            if isinstance(old_channel, discord.TextChannel):
                try:
                    old_message = await old_channel.fetch_message(cfg.message_id)
                    await old_message.delete()
                except discord.NotFound:
                    logging.debug("Honeypot: old verify message already gone.")
                except discord.Forbidden:
                    logging.info(
                        f"Honeypot: no permission to delete old verify message in {old_channel}.")
            else:
                logging.debug("Honeypot: old verify channel no longer exists.")

        cfg.channel_id = channel.id
        cfg.mode = mode
        cfg.message_action = action
        cfg.enabled = True

        # Post the verification message with the persistent button
        embed = _VERIFY_EMBED.copy()
        try:
            msg = await channel.send(embed=embed, view=HoneypotVerifyView())
            cfg.message_id = msg.id
        except discord.Forbidden:
            await interaction.followup.send(
                f"I don't have permission to send messages in {channel.mention}.",
                ephemeral=True)
            return

        await self.bot.database.honeypot_config.save(cfg)

        lines = [
            f"Honeypot enabled in {channel.mention} "
            f"(mode: **{mode}**, action on message: **{action}**)."
        ]
        if mode == "lockdown":
            lines.append(
                "\nFor lockdown mode: create a role that restricts access to all channels "
                "EXCEPT this one, then set it with `/honeypot pending_role @role`.")
        else:
            lines.append(
                "\nFor visibility mode: create a role with a DENY overwrite on this channel, "
                "then set it with `/honeypot verify_role @role`.")
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @honeypot_group.command(name="disable", description="Disable the honeypot")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def honeypot_disable(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        cfg = await self.bot.database.honeypot_config.get(interaction.guild.id)
        if cfg is None or not cfg.enabled:
            await interaction.response.send_message(
                "Honeypot is not enabled.", ephemeral=True)
            return
        cfg.enabled = False
        await self.bot.database.honeypot_config.save(cfg)
        await interaction.response.send_message("Honeypot disabled.", ephemeral=True)

    @honeypot_group.command(
        name="action",
        description="Change what happens when someone sends a message in the honeypot")
    @app_commands.choices(action=[
        app_commands.Choice(name="kick", value="kick"),
        app_commands.Choice(name="ban", value="ban"),
        app_commands.Choice(name="mute 24h", value="mute"),
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def honeypot_action(
        self, interaction: discord.Interaction, action: str
    ) -> None:
        if not interaction.guild:
            return
        cfg = await self.bot.database.honeypot_config.get(interaction.guild.id)
        if cfg is None:
            cfg = Schemas.HoneypotConfig(guild_id=interaction.guild.id)
        cfg.message_action = action
        await self.bot.database.honeypot_config.save(cfg)
        await interaction.response.send_message(
            f"Honeypot action set to **{action}**.", ephemeral=True)

    @honeypot_group.command(
        name="alert_channel",
        description="Set the channel where honeypot trigger alerts are posted")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def honeypot_alert_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        if not interaction.guild:
            return
        cfg = await self.bot.database.honeypot_config.get(interaction.guild.id)
        if cfg is None:
            cfg = Schemas.HoneypotConfig(guild_id=interaction.guild.id)
        cfg.alert_channel_id = channel.id
        await self.bot.database.honeypot_config.save(cfg)
        await interaction.response.send_message(
            f"Alert channel set to {channel.mention}.", ephemeral=True)

    @honeypot_group.command(
        name="verify_role",
        description="Visibility mode: role added on verify (should have DENY overwrite on honeypot)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def honeypot_verify_role(
        self, interaction: discord.Interaction, role: discord.Role
    ) -> None:
        if not interaction.guild:
            return
        cfg = await self.bot.database.honeypot_config.get(interaction.guild.id)
        if cfg is None:
            cfg = Schemas.HoneypotConfig(guild_id=interaction.guild.id)
        cfg.verify_role_id = role.id
        await self.bot.database.honeypot_config.save(cfg)
        await interaction.response.send_message(
            f"Verify role set to {role.mention}.", ephemeral=True)

    @honeypot_group.command(
        name="pending_role",
        description="Lockdown mode: role assigned on join (restricts access until verified)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def honeypot_pending_role(
        self, interaction: discord.Interaction, role: discord.Role
    ) -> None:
        if not interaction.guild:
            return
        cfg = await self.bot.database.honeypot_config.get(interaction.guild.id)
        if cfg is None:
            cfg = Schemas.HoneypotConfig(guild_id=interaction.guild.id)
        cfg.pending_role_id = role.id
        await self.bot.database.honeypot_config.save(cfg)
        await interaction.response.send_message(
            f"Pending role set to {role.mention}.", ephemeral=True)

    @honeypot_group.command(
        name="status", description="Show the current honeypot configuration")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def honeypot_status(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        cfg = await self.bot.database.honeypot_config.get(interaction.guild.id)
        if cfg is None or not cfg.channel_id:
            await interaction.response.send_message(
                "Honeypot is not configured. Use `/honeypot enable` to set it up.",
                ephemeral=True)
            return

        ch = interaction.guild.get_channel(cfg.channel_id or 0)
        alert_ch = interaction.guild.get_channel(cfg.alert_channel_id or 0)
        verify_role = interaction.guild.get_role(cfg.verify_role_id or 0)
        pending_role = interaction.guild.get_role(cfg.pending_role_id or 0)

        embed = discord.Embed(title="Honeypot Status", color=discord.Color.blurple())
        embed.add_field(name="Enabled", value="Yes" if cfg.enabled else "No", inline=True)
        embed.add_field(name="Channel", value=ch.mention if ch else "Not found", inline=True)
        embed.add_field(name="Mode", value=cfg.mode or "visibility", inline=True)
        embed.add_field(name="Action", value=cfg.message_action or "kick", inline=True)
        embed.add_field(
            name="Alert Channel", value=alert_ch.mention if alert_ch else "Not set", inline=True)
        embed.add_field(
            name="Verify Role", value=verify_role.mention if verify_role else "Not set", inline=True)
        embed.add_field(
            name="Pending Role", value=pending_role.mention if pending_role else "Not set", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: KidneyBot) -> None:
    await bot.add_cog(Honeypot(bot))
