# Network — connect multiple servers owned by the same operator for punishment
# sync, shared heuristics, watchlists, raid broadcasting, and tamper-proof logging.
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

from __future__ import annotations

import logging
import secrets
import time
from uuid import uuid4

import discord
from discord import app_commands
from discord.ext import commands

from utils.database import Schemas
from utils.kidney_bot import KidneyBot

# Log channel names created inside the log server
_LOG_CHANNELS = [
    "network-events",
    "bans",
    "kicks",
    "warns",
    "timeouts",
    "heuristics-alerts",
    "honeypot-triggers",
    "raid-alerts",
    "mod-actions",
]

# How long (seconds) a network raid alert elevates thresholds in sibling servers
_RAID_ELEVATION_DURATION = 1800  # 30 minutes


def _network_embed(title: str, desc: str, color: discord.Color) -> discord.Embed:
    embed = discord.Embed(title=title, description=desc, color=color)
    embed.set_footer(text="kidney bot network")
    return embed


class Network(commands.Cog):
    def __init__(self, bot: KidneyBot) -> None:
        self.bot = bot

    # ── Internal helpers ───────────────────────────────────────────────────────

    async def _get_guild_network(self, guild_id: int) -> Schemas.Network | None:
        ngc = await self.bot.database.network_guild_config.get(guild_id)
        if not ngc or not ngc.network_id:
            return None
        return await self.bot.database.networks.get(ngc.network_id)

    async def _post_to_log(
        self,
        network: Schemas.Network,
        channel_key: str,
        embed: discord.Embed,
    ) -> None:
        if not network.log_server_id:
            return
        log_server = self.bot.get_guild(network.log_server_id)
        if not log_server:
            return
        ch_id = network.log_channel_map.get(channel_key)
        if not ch_id:
            return
        ch = log_server.get_channel(ch_id)
        if isinstance(ch, discord.TextChannel):
            try:
                await ch.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

    async def _propagate_ban(
        self,
        network: Schemas.Network,
        source_guild_id: int,
        user_id: int,
        reason: str,
    ) -> list[int]:
        """Attempt to ban user_id in all other network guilds that opt-in. Returns list of guild_ids where applied."""
        applied: list[int] = []
        for gid in network.guild_ids:
            if gid == source_guild_id:
                continue
            guild = self.bot.get_guild(gid)
            if not guild:
                continue
            try:
                await guild.ban(discord.Object(id=user_id), reason=f"[Network sync] {reason}")
                applied.append(gid)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass
        return applied

    async def _setup_log_server_channels(
        self,
        log_server: discord.Guild,
        owner: discord.Member,
        network: Schemas.Network,
    ) -> dict:
        overwrites = {
            log_server.default_role: discord.PermissionOverwrite(view_channel=False),
            log_server.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, embed_links=True,
                read_message_history=True),
            owner: discord.PermissionOverwrite(
                view_channel=True, read_message_history=True),
        }
        category = await log_server.create_category(
            f"Network Logs — {network.name}", overwrites=overwrites)
        channel_map: dict = {}
        for name in _LOG_CHANNELS:
            ch = await log_server.create_text_channel(
                name, category=category, overwrites=overwrites)
            channel_map[name.replace("-", "_")] = ch.id
        return channel_map

    # ── Event listeners ───────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        logging.info("Network cog loaded.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Watchlist check is handled in heuristics.py via 'watchlist_hit' dispatch."""
        pass

    @commands.Cog.listener()
    async def on_watchlist_hit(
        self,
        guild: discord.Guild,
        member: discord.Member,
        watchlist_entry: dict,
        network: Schemas.Network,
    ) -> None:
        reason = watchlist_entry.get("reason", "No reason provided")
        added_by_id = watchlist_entry.get("added_by")

        # Alert in the guild's configured alert channel
        ngc = await self.bot.database.network_guild_config.get(guild.id)
        heuristics_cfg = await self.bot.database.heuristics_config.get(guild.id)
        alert_ch_id = heuristics_cfg.alert_channel_id if heuristics_cfg else None
        if alert_ch_id:
            alert_ch = guild.get_channel(alert_ch_id)
            if isinstance(alert_ch, discord.TextChannel):
                embed = discord.Embed(
                    title="⚠️  Network Watchlist — Member Joined",
                    description=(
                        f"{member.mention} (`{member.id}`) is on the network watchlist.\n"
                        f"**Reason:** {reason}"
                    ),
                    color=discord.Color.dark_orange(),
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                try:
                    await alert_ch.send(embed=embed)
                except discord.Forbidden:
                    pass

        # Log to tamper-proof server
        embed = discord.Embed(
            title="Watchlist Hit",
            description=(
                f"**User:** {member} (`{member.id}`)\n"
                f"**Server:** {guild.name} (`{guild.id}`)\n"
                f"**Reason:** {reason}"
            ),
            color=discord.Color.dark_orange(),
        )
        await self._post_to_log(network, "network_events", embed)

    @commands.Cog.listener()
    async def on_modlog_entry(
        self,
        entry: Schemas.ModLogEntry,
        guild: discord.Guild,
    ) -> None:
        """Receives every modlog action from moderation.py and honeypot.py."""
        network = await self._get_guild_network(guild.id)
        if not network:
            return

        # Log all actions to tamper-proof server
        channel_key_map = {
            "ban": "bans", "kick": "kicks", "warn": "warns",
            "mute": "timeouts", "tempmute": "timeouts",
        }
        ch_key = channel_key_map.get(entry.action_type or "", "mod_actions")
        actor = guild.get_member(entry.moderator_id or 0)
        target = f"<@{entry.user_id}> (`{entry.user_id}`)"
        embed = discord.Embed(
            title=f"{(entry.action_type or 'action').upper()} — {guild.name}",
            description=(
                f"**Target:** {target}\n"
                f"**Moderator:** {actor.mention if actor else entry.moderator_id}\n"
                f"**Reason:** {entry.reason or 'No reason'}"
            ),
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        await self._post_to_log(network, ch_key, embed)
        await self._post_to_log(network, "mod_actions", embed)

        # Propagate bans to sibling servers
        if entry.action_type == "ban" and network.propagate_bans and entry.user_id:
            applied = await self._propagate_ban(
                network, guild.id, entry.user_id, entry.reason or "Network-synced ban")
            if applied:
                names = ", ".join(
                    g.name for gid in applied
                    if (g := self.bot.get_guild(gid)))
                sync_embed = discord.Embed(
                    title="Network Ban Synced",
                    description=(
                        f"Ban for <@{entry.user_id}> propagated from **{guild.name}** to: "
                        f"{names}"
                    ),
                    color=discord.Color.dark_red(),
                )
                await self._post_to_log(network, "network_events", sync_embed)

        # Propagate kicks
        if entry.action_type == "kick" and network.propagate_kicks and entry.user_id:
            for gid in network.guild_ids:
                if gid == guild.id:
                    continue
                sibling = self.bot.get_guild(gid)
                if not sibling:
                    continue
                sibling_member = sibling.get_member(entry.user_id)
                if sibling_member:
                    try:
                        await sibling_member.kick(
                            reason=f"[Network sync] {entry.reason or 'Kick from sibling server'}")
                    except (discord.Forbidden, discord.HTTPException):
                        pass

        # Propagate mutes (timeouts)
        if entry.action_type in ("mute", "tempmute") and network.propagate_mutes and entry.user_id:
            from datetime import timedelta
            duration = entry.duration or 86400
            for gid in network.guild_ids:
                if gid == guild.id:
                    continue
                sibling = self.bot.get_guild(gid)
                if not sibling:
                    continue
                sibling_member = sibling.get_member(entry.user_id)
                if sibling_member:
                    try:
                        await sibling_member.timeout(
                            timedelta(seconds=duration),
                            reason=f"[Network sync] {entry.reason or 'Mute from sibling server'}")
                    except (discord.Forbidden, discord.HTTPException):
                        pass

    @commands.Cog.listener()
    async def on_raid_alert(self, source_guild: discord.Guild, member_count: int) -> None:
        """Dispatched by heuristics.py when join cluster threshold is crossed."""
        network = await self._get_guild_network(source_guild.id)
        if not network or not network.sync_raid_alerts:
            return

        # Elevate all sibling guilds
        for gid in network.guild_ids:
            if gid != source_guild.id:
                self.bot.dispatch('guild_elevated', gid, _RAID_ELEVATION_DURATION)

        # Log to tamper-proof server
        embed = discord.Embed(
            title="🚨 Raid Alert Broadcast",
            description=(
                f"**Source:** {source_guild.name} (`{source_guild.id}`)\n"
                f"**Joins detected:** {member_count} in cluster window\n"
                f"All sibling servers elevated for {_RAID_ELEVATION_DURATION // 60} minutes."
            ),
            color=discord.Color.dark_red(),
            timestamp=discord.utils.utcnow(),
        )
        await self._post_to_log(network, "raid_alerts", embed)

        # Alert in other guilds' configured alert channels
        for gid in network.guild_ids:
            if gid == source_guild.id:
                continue
            guild = self.bot.get_guild(gid)
            if not guild:
                continue
            hcfg = await self.bot.database.heuristics_config.get(gid)
            if hcfg and hcfg.alert_channel_id:
                alert_ch = guild.get_channel(hcfg.alert_channel_id)
                if isinstance(alert_ch, discord.TextChannel):
                    try:
                        await alert_ch.send(embed=discord.Embed(
                            title="🚨 Network Raid Alert",
                            description=(
                                f"A raid was detected in **{source_guild.name}** "
                                f"({member_count} joins). This server's thresholds are "
                                f"elevated for {_RAID_ELEVATION_DURATION // 60} minutes."
                            ),
                            color=discord.Color.dark_red(),
                        ))
                    except discord.Forbidden:
                        pass

    @commands.Cog.listener()
    async def on_honeypot_trigger(
        self,
        guild: discord.Guild,
        member: discord.Member,
        action: str,
        content: str,
    ) -> None:
        network = await self._get_guild_network(guild.id)
        if not network:
            return
        embed = discord.Embed(
            title="Honeypot Triggered",
            description=(
                f"**User:** {member} (`{member.id}`)\n"
                f"**Server:** {guild.name}\n"
                f"**Action taken:** {action}\n"
                f"**Message:** {content[:500] or '*(no text)*'}"
            ),
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )
        await self._post_to_log(network, "honeypot_triggers", embed)

    # ── /network group ─────────────────────────────────────────────────────────

    network_group = app_commands.Group(
        name="network",
        description="Manage a cross-server network for punishment sync and shared intelligence",
    )

    # ── Core management ────────────────────────────────────────────────────────

    @network_group.command(
        name="create", description="Create a new server network (you become the owner)")
    @app_commands.describe(name="Name for this network (visible in log server and status)")
    @app_commands.checks.has_permissions(administrator=True)
    async def network_create(
        self, interaction: discord.Interaction, name: str
    ) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)

        # Check if guild is already in a network
        existing_ngc = await self.bot.database.network_guild_config.get(interaction.guild.id)
        if existing_ngc and existing_ngc.network_id:
            await interaction.followup.send(
                "This server is already in a network. Leave it first with `/network leave`.",
                ephemeral=True)
            return

        # Check if user already owns a network
        existing_net = await self.bot.database.networks.get_by_owner(interaction.user.id)
        if existing_net:
            await interaction.followup.send(
                f"You already own the network **{existing_net.name}**. "
                f"Disband it first with `/network disband`.",
                ephemeral=True)
            return

        network = Schemas.Network(
            id=str(uuid4()),
            name=name,
            owner_id=interaction.user.id,
            guild_ids=[interaction.guild.id],
        )
        await self.bot.database.networks.save(network)

        ngc = Schemas.NetworkGuildConfig(
            guild_id=interaction.guild.id, network_id=network.id)
        await self.bot.database.network_guild_config.save(ngc)

        await interaction.followup.send(
            f"Network **{name}** created! This server is the first member.\n"
            f"Use `/network invite` to generate a code for other servers to join.",
            ephemeral=True)

    @network_group.command(
        name="invite", description="Generate a one-time join code for another server")
    @app_commands.describe(expiry_hours="Hours until the code expires (default 24)")
    @app_commands.checks.has_permissions(administrator=True)
    async def network_invite(
        self, interaction: discord.Interaction, expiry_hours: int = 24
    ) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)

        network = await self._get_guild_network(interaction.guild.id)
        if not network:
            await interaction.followup.send(
                "This server is not in a network.", ephemeral=True)
            return
        if network.owner_id != interaction.user.id:
            await interaction.followup.send(
                "Only the network owner can generate invite codes.", ephemeral=True)
            return

        code = secrets.token_urlsafe(16)
        network.invite_code = code
        network.invite_expires_at = int(time.time()) + expiry_hours * 3600
        await self.bot.database.networks.save(network)

        await interaction.followup.send(
            f"Invite code: `{code}`\n"
            f"Expires in {expiry_hours} hour(s). "
            f"Have the other server's admin run `/network join {code}`.",
            ephemeral=True)

    @network_group.command(
        name="join", description="Join a network using an invite code")
    @app_commands.describe(code="The invite code provided by the network owner")
    @app_commands.checks.has_permissions(administrator=True)
    async def network_join(
        self, interaction: discord.Interaction, code: str
    ) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)

        # Already in a network?
        existing_ngc = await self.bot.database.network_guild_config.get(interaction.guild.id)
        if existing_ngc and existing_ngc.network_id:
            await interaction.followup.send(
                "This server is already in a network. Leave it first with `/network leave`.",
                ephemeral=True)
            return

        # Find network with this invite code
        network = await self.bot.database.networks.query_one({"invite_code": code})
        if not network:
            await interaction.followup.send(
                "Invalid or expired invite code.", ephemeral=True)
            return

        now = int(time.time())
        if network.invite_expires_at and network.invite_expires_at < now:
            await interaction.followup.send(
                "This invite code has expired.", ephemeral=True)
            return

        # Add guild to network and clear the invite
        network.guild_ids.append(interaction.guild.id)
        network.invite_code = None
        network.invite_expires_at = None
        await self.bot.database.networks.save(network)

        ngc = Schemas.NetworkGuildConfig(
            guild_id=interaction.guild.id, network_id=network.id)
        await self.bot.database.network_guild_config.save(ngc)

        # Log the join
        embed = discord.Embed(
            title="Server Joined Network",
            description=f"**{interaction.guild.name}** (`{interaction.guild.id}`) joined.",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        await self._post_to_log(network, "network_events", embed)

        await interaction.followup.send(
            f"This server has joined network **{network.name}**! "
            f"There are now {len(network.guild_ids)} servers in the network.",
            ephemeral=True)

    @network_group.command(
        name="leave", description="Remove this server from the network")
    @app_commands.checks.has_permissions(administrator=True)
    async def network_leave(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)

        network = await self._get_guild_network(interaction.guild.id)
        if not network:
            await interaction.followup.send(
                "This server is not in a network.", ephemeral=True)
            return
        if network.owner_id == interaction.user.id and len(network.guild_ids) > 1:
            await interaction.followup.send(
                "You are the network owner. Transfer ownership or disband the network "
                "with `/network disband` before leaving.",
                ephemeral=True)
            return

        network.guild_ids = [g for g in network.guild_ids if g != interaction.guild.id]
        if network.guild_ids:
            await self.bot.database.networks.save(network)
        else:
            await self.bot.database.networks.delete(network.id)

        await self.bot.database.network_guild_config.delete(interaction.guild.id)

        embed = discord.Embed(
            title="Server Left Network",
            description=f"**{interaction.guild.name}** left the network.",
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )
        await self._post_to_log(network, "network_events", embed)

        await interaction.followup.send("This server has left the network.", ephemeral=True)

    @network_group.command(
        name="disband", description="Dissolve the entire network (owner only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def network_disband(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)

        network = await self._get_guild_network(interaction.guild.id)
        if not network:
            await interaction.followup.send(
                "This server is not in a network.", ephemeral=True)
            return
        if network.owner_id != interaction.user.id:
            await interaction.followup.send(
                "Only the network owner can disband the network.", ephemeral=True)
            return

        for gid in network.guild_ids:
            await self.bot.database.network_guild_config.delete(gid)
        await self.bot.database.networks.delete(network.id or "")

        await interaction.followup.send(
            f"Network **{network.name}** has been disbanded.", ephemeral=True)

    @network_group.command(
        name="members", description="List all servers in the network")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def network_members(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)

        network = await self._get_guild_network(interaction.guild.id)
        if not network:
            await interaction.followup.send(
                "This server is not in a network.", ephemeral=True)
            return

        lines = []
        for gid in network.guild_ids:
            guild = self.bot.get_guild(gid)
            name = guild.name if guild else f"Unknown (`{gid}`)"
            tag = " *(this server)*" if gid == interaction.guild.id else ""
            tag += " *(log server)*" if gid == network.log_server_id else ""
            lines.append(f"• {name}{tag}")

        embed = discord.Embed(
            title=f"Network: {network.name}",
            description="\n".join(lines) or "No members.",
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"{len(network.guild_ids)} server(s) in network")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @network_group.command(
        name="status", description="Show network configuration for this server")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def network_status(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)

        ngc = await self.bot.database.network_guild_config.get(interaction.guild.id)
        if not ngc or not ngc.network_id:
            await interaction.followup.send(
                "This server is not in a network. Create one with `/network create`.",
                ephemeral=True)
            return

        network = await self.bot.database.networks.get(ngc.network_id)
        if not network:
            await interaction.followup.send("Network data not found.", ephemeral=True)
            return

        log_server = self.bot.get_guild(network.log_server_id or 0)
        owner = self.bot.get_user(network.owner_id or 0)

        embed = discord.Embed(
            title=f"Network: {network.name}", color=discord.Color.blurple())
        embed.add_field(name="Owner", value=owner.mention if owner else str(network.owner_id), inline=True)
        embed.add_field(name="Servers", value=str(len(network.guild_ids)), inline=True)
        embed.add_field(
            name="Log Server",
            value=log_server.name if log_server else "Not set",
            inline=True)
        embed.add_field(
            name="Sync Settings",
            value=(
                f"Bans: {'✅' if network.propagate_bans else '❌'}  "
                f"Kicks: {'✅' if network.propagate_kicks else '❌'}  "
                f"Mutes: {'✅' if network.propagate_mutes else '❌'}\n"
                f"Heuristics: {'✅' if network.share_heuristics else '❌'}  "
                f"Raid Alerts: {'✅' if network.sync_raid_alerts else '❌'}"
            ),
            inline=False,
        )
        embed.add_field(
            name="Role in Network",
            value="Log Server" if ngc.is_log_server else "Member Server",
            inline=True,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Sync settings subgroup ─────────────────────────────────────────────────

    sync_group = app_commands.Group(
        name="sync",
        description="Toggle network sync settings",
        parent=network_group,
    )

    async def _toggle_sync(
        self,
        interaction: discord.Interaction,
        field: str,
        enabled: bool,
        label: str,
    ) -> None:
        if not interaction.guild:
            return
        network = await self._get_guild_network(interaction.guild.id)
        if not network:
            await interaction.response.send_message(
                "This server is not in a network.", ephemeral=True)
            return
        if network.owner_id != interaction.user.id:
            await interaction.response.send_message(
                "Only the network owner can change sync settings.", ephemeral=True)
            return
        setattr(network, field, enabled)
        await self.bot.database.networks.save(network)
        await interaction.response.send_message(
            f"Network {label} sync {'enabled' if enabled else 'disabled'}.",
            ephemeral=True)

    @sync_group.command(name="bans", description="Sync bans across the network")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_bans(self, interaction: discord.Interaction, enabled: bool) -> None:
        await self._toggle_sync(interaction, "propagate_bans", enabled, "ban")

    @sync_group.command(name="kicks", description="Sync kicks across the network")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_kicks(self, interaction: discord.Interaction, enabled: bool) -> None:
        await self._toggle_sync(interaction, "propagate_kicks", enabled, "kick")

    @sync_group.command(name="mutes", description="Sync mutes across the network")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_mutes(self, interaction: discord.Interaction, enabled: bool) -> None:
        await self._toggle_sync(interaction, "propagate_mutes", enabled, "mute")

    @sync_group.command(name="heuristics", description="Share heuristics reputation across the network")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_heuristics(self, interaction: discord.Interaction, enabled: bool) -> None:
        await self._toggle_sync(interaction, "share_heuristics", enabled, "heuristics")

    @sync_group.command(name="raids", description="Broadcast raid alerts to sibling servers")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_raids(self, interaction: discord.Interaction, enabled: bool) -> None:
        await self._toggle_sync(interaction, "sync_raid_alerts", enabled, "raid alert")

    # ── Watchlist subgroup ────────────────────────────────────────────────────

    watchlist_group = app_commands.Group(
        name="watchlist",
        description="Network watchlist — get alerted when watched users join any server",
        parent=network_group,
    )

    @watchlist_group.command(
        name="add",
        description="Add a user to the network watchlist")
    @app_commands.describe(user_id="Discord user ID", reason="Why this user is being watched")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def watchlist_add(
        self,
        interaction: discord.Interaction,
        user_id: str,
        reason: str = "No reason provided",
    ) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)

        network = await self._get_guild_network(interaction.guild.id)
        if not network:
            await interaction.followup.send(
                "This server is not in a network.", ephemeral=True)
            return

        try:
            uid = int(user_id)
        except ValueError:
            await interaction.followup.send("Invalid user ID.", ephemeral=True)
            return

        if any(w.get('user_id') == uid for w in network.watchlist):
            await interaction.followup.send(
                "User is already on the watchlist.", ephemeral=True)
            return

        network.watchlist.append({
            "user_id": uid,
            "reason": reason,
            "added_by": interaction.user.id,
            "added_at": int(time.time()),
        })
        await self.bot.database.networks.save(network)

        embed = discord.Embed(
            title="Watchlist Entry Added",
            description=f"**User:** <@{uid}> (`{uid}`)\n**Reason:** {reason}",
            color=discord.Color.orange(),
        )
        await self._post_to_log(network, "network_events", embed)
        await interaction.followup.send(
            f"User `{uid}` added to network watchlist.", ephemeral=True)

    @watchlist_group.command(
        name="remove", description="Remove a user from the network watchlist")
    @app_commands.describe(user_id="Discord user ID to remove")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def watchlist_remove(
        self, interaction: discord.Interaction, user_id: str
    ) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)

        network = await self._get_guild_network(interaction.guild.id)
        if not network:
            await interaction.followup.send(
                "This server is not in a network.", ephemeral=True)
            return

        try:
            uid = int(user_id)
        except ValueError:
            await interaction.followup.send("Invalid user ID.", ephemeral=True)
            return

        before = len(network.watchlist)
        network.watchlist = [w for w in network.watchlist if w.get('user_id') != uid]
        if len(network.watchlist) == before:
            await interaction.followup.send(
                "User is not on the watchlist.", ephemeral=True)
            return

        await self.bot.database.networks.save(network)
        await interaction.followup.send(
            f"User `{uid}` removed from network watchlist.", ephemeral=True)

    @watchlist_group.command(
        name="list", description="List all users on the network watchlist")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def watchlist_list(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)

        network = await self._get_guild_network(interaction.guild.id)
        if not network:
            await interaction.followup.send(
                "This server is not in a network.", ephemeral=True)
            return

        if not network.watchlist:
            await interaction.followup.send(
                "The watchlist is empty.", ephemeral=True)
            return

        lines = []
        for entry in network.watchlist:
            uid = entry.get('user_id', '?')
            reason = entry.get('reason', 'No reason')
            lines.append(f"• <@{uid}> (`{uid}`) — {reason}")

        embed = discord.Embed(
            title=f"Watchlist — {network.name}",
            description="\n".join(lines[:25]),
            color=discord.Color.orange(),
        )
        embed.set_footer(text=f"{len(network.watchlist)} entries")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Network-wide ban / pardon ──────────────────────────────────────────────

    @network_group.command(
        name="ban",
        description="Ban a user from all servers in the network simultaneously")
    @app_commands.describe(
        user_id="Discord user ID to ban", reason="Reason for the ban")
    @app_commands.checks.has_permissions(ban_members=True)
    async def network_ban(
        self,
        interaction: discord.Interaction,
        user_id: str,
        reason: str = "Network-wide ban",
    ) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)

        network = await self._get_guild_network(interaction.guild.id)
        if not network:
            await interaction.followup.send(
                "This server is not in a network.", ephemeral=True)
            return

        try:
            uid = int(user_id)
        except ValueError:
            await interaction.followup.send("Invalid user ID.", ephemeral=True)
            return

        applied = await self._propagate_ban(network, -1, uid, reason)
        # Also ban in source guild
        try:
            await interaction.guild.ban(discord.Object(id=uid), reason=reason)
            applied.insert(0, interaction.guild.id)
        except (discord.Forbidden, discord.HTTPException):
            pass

        if not applied:
            await interaction.followup.send(
                "Could not ban in any server (missing permissions?).", ephemeral=True)
            return

        guild_names = ", ".join(
            g.name for gid in applied if (g := self.bot.get_guild(gid)))
        embed = discord.Embed(
            title="Network-Wide Ban",
            description=(
                f"**User:** <@{uid}> (`{uid}`)\n"
                f"**Reason:** {reason}\n"
                f"**Applied in:** {guild_names}"
            ),
            color=discord.Color.dark_red(),
            timestamp=discord.utils.utcnow(),
        )
        await self._post_to_log(network, "bans", embed)
        await interaction.followup.send(
            f"Banned user `{uid}` in {len(applied)} server(s).", ephemeral=True)

    @network_group.command(
        name="pardon",
        description="Unban a user from all network servers and remove from watchlist")
    @app_commands.describe(user_id="Discord user ID to pardon")
    @app_commands.checks.has_permissions(ban_members=True)
    async def network_pardon(
        self, interaction: discord.Interaction, user_id: str
    ) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)

        network = await self._get_guild_network(interaction.guild.id)
        if not network:
            await interaction.followup.send(
                "This server is not in a network.", ephemeral=True)
            return

        try:
            uid = int(user_id)
        except ValueError:
            await interaction.followup.send("Invalid user ID.", ephemeral=True)
            return

        unbanned: list[int] = []
        for gid in network.guild_ids:
            guild = self.bot.get_guild(gid)
            if not guild:
                continue
            try:
                await guild.unban(discord.Object(id=uid), reason="Network pardon")
                unbanned.append(gid)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

        # Remove from watchlist
        before = len(network.watchlist)
        network.watchlist = [w for w in network.watchlist if w.get('user_id') != uid]
        removed_from_wl = len(network.watchlist) < before
        await self.bot.database.networks.save(network)

        embed = discord.Embed(
            title="Network Pardon",
            description=(
                f"**User:** <@{uid}> (`{uid}`)\n"
                f"Unbanned in {len(unbanned)} server(s)."
                + (" Removed from watchlist." if removed_from_wl else "")
            ),
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        await self._post_to_log(network, "network_events", embed)
        await interaction.followup.send(
            f"Pardoned user `{uid}` in {len(unbanned)} server(s)."
            + (" Removed from watchlist." if removed_from_wl else ""),
            ephemeral=True)

    # ── Log server subgroup ────────────────────────────────────────────────────

    logserver_group = app_commands.Group(
        name="logserver",
        description="Manage the tamper-proof log server",
        parent=network_group,
    )

    @logserver_group.command(
        name="set",
        description="Set up a server as the tamper-proof log server for this network")
    @app_commands.describe(
        server_id="ID of the server to use as the log server (bot must be in it)")
    @app_commands.checks.has_permissions(administrator=True)
    async def logserver_set(
        self, interaction: discord.Interaction, server_id: str
    ) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)

        network = await self._get_guild_network(interaction.guild.id)
        if not network:
            await interaction.followup.send(
                "This server is not in a network.", ephemeral=True)
            return
        if network.owner_id != interaction.user.id:
            await interaction.followup.send(
                "Only the network owner can set the log server.", ephemeral=True)
            return

        try:
            lsid = int(server_id)
        except ValueError:
            await interaction.followup.send("Invalid server ID.", ephemeral=True)
            return

        log_server = self.bot.get_guild(lsid)
        if not log_server:
            await interaction.followup.send(
                "Bot is not in that server. Add the bot first.", ephemeral=True)
            return

        if lsid in network.guild_ids:
            await interaction.followup.send(
                "The log server cannot be a member of the network itself. "
                "Create a separate, dedicated server.",
                ephemeral=True)
            return

        # Verify caller is admin in the log server
        owner_as_log_member = log_server.get_member(interaction.user.id)
        if not owner_as_log_member or not owner_as_log_member.guild_permissions.administrator:
            await interaction.followup.send(
                "You must be an administrator in the log server.", ephemeral=True)
            return

        # Create the tamper-proof channels
        try:
            channel_map = await self._setup_log_server_channels(
                log_server, owner_as_log_member, network)
        except discord.Forbidden:
            await interaction.followup.send(
                "I don't have permission to create channels in that server.", ephemeral=True)
            return

        network.log_server_id = lsid
        network.log_channel_map = channel_map
        await self.bot.database.networks.save(network)

        # Mark it as the log server in network_guild_config
        log_ngc = await self.bot.database.network_guild_config.get(lsid)
        if log_ngc is None:
            log_ngc = Schemas.NetworkGuildConfig(guild_id=lsid)
        log_ngc.is_log_server = True
        log_ngc.network_id = network.id
        await self.bot.database.network_guild_config.save(log_ngc)

        embed = discord.Embed(
            title="Log Server Configured",
            description=(
                f"**{log_server.name}** is now the tamper-proof log server for "
                f"network **{network.name}**.\n\n"
                "All moderation actions, honeypot triggers, raid alerts, and network "
                "events will be mirrored here. Only you and the bot can see these channels."
            ),
            color=discord.Color.green(),
        )
        await self._post_to_log(network, "network_events", embed)
        await interaction.followup.send(
            f"Log server set to **{log_server.name}**. "
            f"{len(channel_map)} log channels created.",
            ephemeral=True)

    @logserver_group.command(
        name="unset", description="Remove the tamper-proof log server")
    @app_commands.checks.has_permissions(administrator=True)
    async def logserver_unset(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)

        network = await self._get_guild_network(interaction.guild.id)
        if not network:
            await interaction.followup.send(
                "This server is not in a network.", ephemeral=True)
            return
        if network.owner_id != interaction.user.id:
            await interaction.followup.send(
                "Only the network owner can change the log server.", ephemeral=True)
            return
        if not network.log_server_id:
            await interaction.followup.send(
                "No log server is set.", ephemeral=True)
            return

        old_lsid = network.log_server_id
        network.log_server_id = None
        network.log_channel_map = {}
        await self.bot.database.networks.save(network)

        # Clear the log server flag
        log_ngc = await self.bot.database.network_guild_config.get(old_lsid)
        if log_ngc:
            log_ngc.is_log_server = False
            log_ngc.network_id = None
            await self.bot.database.network_guild_config.save(log_ngc)

        await interaction.followup.send("Log server removed.", ephemeral=True)

    @logserver_group.command(
        name="test", description="Post a test message to the log server to verify connectivity")
    @app_commands.checks.has_permissions(administrator=True)
    async def logserver_test(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)

        network = await self._get_guild_network(interaction.guild.id)
        if not network or not network.log_server_id:
            await interaction.followup.send(
                "No log server configured.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Log Server Test",
            description=f"Test message from **{interaction.guild.name}**. Log server is working!",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        await self._post_to_log(network, "network_events", embed)
        await interaction.followup.send("Test message sent to log server.", ephemeral=True)


async def setup(bot: KidneyBot) -> None:
    await bot.add_cog(Network(bot))
