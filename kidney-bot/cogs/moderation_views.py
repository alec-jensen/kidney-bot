# Moderation-specific Discord UI components.
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

from __future__ import annotations

import logging
import re
import time
from datetime import timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

import discord
import humanize

from utils.database import Schemas
from utils.kidney_bot import KidneyBot
from utils.types import AnyUser

if TYPE_CHECKING:
    from cogs.moderation import Moderation
    from utils.mod_insight import InsightResult, SuggestedAction

ITEMS_PER_PAGE = 5

ACTION_COLORS: dict[str, discord.Color] = {
    "warn": discord.Color.yellow(),
    "mute": discord.Color.orange(),
    "tempmute": discord.Color.orange(),
    "kick": discord.Color.red(),
    "ban": discord.Color.dark_red(),
    "unmute": discord.Color.green(),
    "unban": discord.Color.green(),
    "nickname": discord.Color.blurple(),
    "purge": discord.Color.greyple(),
}

ACTION_LABELS: dict[str, str] = {
    "warn": "⚠️ Warn",
    "mute": "🔇 Mute",
    "tempmute": "⏱️ Timeout",
    "kick": "👢 Kick",
    "ban": "🔨 Ban",
    "unmute": "🔊 Unmute",
    "unban": "✅ Unban",
    "nickname": "✏️ Nickname",
    "purge": "🧹 Purge",
}

# (label, description, seconds) — shown in ban delete-history dropdowns.
_DELETE_WINDOW_OPTIONS: list[tuple[str, str, int]] = [
    ("Don't delete", "Keep all message history", 0),
    ("Last hour", "Delete messages from the past hour", 3600),
    ("Last 6 hours", "Delete messages from the past 6 hours", 21600),
    ("Last 24 hours", "Delete messages from the past 24 hours", 86400),
    ("Last 7 days", "Delete messages from the past 7 days (maximum)", 604800),
]


def _format_delete_window(seconds: int) -> str:
    for label, _, val in _DELETE_WINDOW_OPTIONS:
        if val == seconds:
            return label
    return f"{seconds // 3600}h" if seconds >= 3600 else f"{seconds}s"


class _BanDeleteSelect(discord.ui.Select):
    """Shared delete-history dropdown used in every ban confirmation view."""

    def __init__(self) -> None:
        options = [
            discord.SelectOption(
                label=label, description=desc, value=str(val), default=(val == 0)
            )
            for label, desc, val in _DELETE_WINDOW_OPTIONS
        ]
        super().__init__(
            placeholder="Delete message history...",
            options=options, min_values=1, max_values=1, row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.delete_seconds = int(self.values[0])  # type: ignore[union-attr]
        await interaction.response.defer()


# ── Review-queue ban confirmation view ────────────────────────────────────────

class _ReviewBanConfirmView(discord.ui.View):
    """
    Shown as an ephemeral follow-up when a mod clicks the Ban button on a
    review-queue card.  Lets them choose how far back to delete messages before
    the ban is actually executed.
    """

    def __init__(
        self,
        user_id: int,
        original_message: discord.Message | None = None,
    ) -> None:
        super().__init__(timeout=120)
        self.user_id = user_id
        self.original_message = original_message
        self.delete_seconds: int = 0
        self.add_item(_BanDeleteSelect())

    @discord.ui.button(
        label="Confirm Ban", style=discord.ButtonStyle.danger, row=1, emoji="🔨"
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Must be used in a server.", ephemeral=True)
            return
        if not interaction.user.guild_permissions.ban_members:
            await interaction.response.send_message(
                "You don't have permission to ban.", ephemeral=True)
            return

        await interaction.response.defer()

        try:
            await interaction.guild.ban(
                discord.Object(self.user_id),
                reason=f"Heuristics review: banned by {interaction.user}",
                delete_message_seconds=self.delete_seconds,
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "I don't have permission to ban that user.", ephemeral=True)
            return
        except discord.NotFound:
            pass  # Already gone; still record and resolve

        bot: KidneyBot = interaction.client  # type: ignore[assignment]
        entry = Schemas.ModLogEntry(
            id=str(uuid4()),
            guild_id=interaction.guild.id,
            user_id=self.user_id,
            moderator_id=interaction.user.id,
            action_type="ban",
            reason=f"Heuristics review queue (banned by {interaction.user})",
            timestamp=int(time.time()),
        )
        await bot.database.mod_log.save(entry)
        bot.dispatch('modlog_entry', entry, interaction.guild)

        result_embed = discord.Embed(
            title="Banned",
            description=f"<@{self.user_id}> has been banned.",
            color=discord.Color.dark_red(),
        )
        if self.delete_seconds > 0:
            result_embed.add_field(
                name="Message history deleted",
                value=_format_delete_window(self.delete_seconds),
                inline=True,
            )

        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(embed=result_embed, view=self)

        # Update the original review-queue card to show it's been resolved.
        if self.original_message:
            try:
                if self.original_message.embeds:
                    embed = self.original_message.embeds[0]
                    embed.color = discord.Color.dark_red()
                    embed.set_footer(text=f"Banned by {interaction.user}")
                    await self.original_message.edit(embed=embed, view=discord.ui.View())
            except (discord.NotFound, discord.Forbidden):
                pass

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, row=1)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Cancelled.", embed=None, view=self)


# ── Insight-view ban: pre-ban select + reason modal ───────────────────────────

class _BanWithDeleteModal(discord.ui.Modal, title="Confirm Ban"):
    """Collects the ban reason after the mod picks a delete window in _InsightBanView."""

    reason: discord.ui.TextInput = discord.ui.TextInput(
        label="Reason (optional)",
        required=False,
        max_length=512,
        placeholder="Enter a reason for this ban...",
    )

    def __init__(
        self,
        suggestion: SuggestedAction,
        cog: Moderation,
        target: discord.Member,
        delete_seconds: int,
    ) -> None:
        super().__init__()
        self.suggestion = suggestion
        self.cog = cog
        self.target = target
        self.delete_seconds = delete_seconds

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Cannot execute this action here.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        reason = self.reason.value or None

        try:
            entry = await self.cog._execute_ban(
                self.target, interaction.user, interaction.guild, reason,
                delete_message_seconds=self.delete_seconds,
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "Missing permissions to ban that user.", ephemeral=True)
            return
        except discord.NotFound:
            await interaction.followup.send(
                "User not found — they may have already left.", ephemeral=True)
            return
        except ValueError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return

        insight = await self.cog._get_insight(self.target, interaction.guild)
        await self.cog._post_to_log_channel(
            interaction.guild, entry, insight, interaction.user, self.target)
        await self.cog._send_insight(interaction, self.target, insight)

        embed = discord.Embed(
            title="Banned",
            description=f"{self.target.mention} has been banned.",
            color=discord.Color.dark_red(),
        )
        if self.delete_seconds > 0:
            embed.add_field(
                name="Message history deleted",
                value=_format_delete_window(self.delete_seconds),
                inline=True,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)


class _InsightBanView(discord.ui.View):
    """
    Shown when a mod clicks the Ban button in the mod-insight action panel.
    Lets them choose a delete window before a reason modal opens.
    """

    def __init__(
        self,
        suggestion: SuggestedAction,
        cog: Moderation,
        target: discord.Member,
    ) -> None:
        super().__init__(timeout=120)
        self.suggestion = suggestion
        self.cog = cog
        self.target = target
        self.delete_seconds: int = 0
        self.add_item(_BanDeleteSelect())

    @discord.ui.button(
        label="Confirm Ban", style=discord.ButtonStyle.danger, row=1, emoji="🔨"
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(
            _BanWithDeleteModal(
                self.suggestion, self.cog, self.target, self.delete_seconds)
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, row=1)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Cancelled.", embed=None, view=self)


class PageDropdown(discord.ui.Select):
    def __init__(self, num_pages: int):
        options = [
            discord.SelectOption(label=str(i + 1), value=str(i + 1))
            for i in range(min(num_pages, 25))
        ]
        super().__init__(placeholder="Select a page...", min_values=1, max_values=1, options=options, row=0)

    async def callback(self, interaction: discord.Interaction) -> None:
        if not isinstance(self.view, ModerationHistoryView):
            return
        self.view.page = int(self.values[0]) - 1
        await self.view.update(interaction)


class ModerationHistoryView(discord.ui.View):
    def __init__(self, bot: KidneyBot, target: AnyUser, guild: discord.Guild | None):
        super().__init__(timeout=300)
        self.bot = bot
        self.target = target
        self.guild = guild
        self.page = 0
        self.entries: list = []
        self.num_pages = 0
        self.message: discord.Message | None = None

    async def async_init(self) -> None:
        if self.guild is None or not isinstance(self.target, discord.Member):
            self.add_item(discord.ui.Button(
                label="No history — user not in guild",
                style=discord.ButtonStyle.secondary,
                disabled=True,
            ))
            return

        self.entries = await self.bot.database.mod_log.get_user_history(
            self.target.id, self.guild.id, limit=500)
        self.entries.sort(key=lambda e: e.timestamp or 0, reverse=True)

        if not self.entries:
            self.add_item(discord.ui.Button(
                label="No moderation history",
                style=discord.ButtonStyle.secondary,
                disabled=True,
            ))
            _disable_nav(self)
            return

        self.num_pages = (len(self.entries) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        if self.num_pages > 1:
            self.add_item(PageDropdown(self.num_pages))

        _update_nav(self)

    def _build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"Moderation History: {self.target}",
            color=discord.Color.red(),
        )
        start = self.page * ITEMS_PER_PAGE
        for entry in self.entries[start:start + ITEMS_PER_PAGE]:
            label = ACTION_LABELS.get(entry.action_type or "", entry.action_type or "Action")
            lines = [f"**Reason:** {entry.reason or 'No reason provided'}"]
            if entry.duration:
                lines.append(f"**Duration:** {humanize.precisedelta(timedelta(seconds=entry.duration), format='%0.0f')}")
            lines.append(f"**Moderator:** <@{entry.moderator_id}>")
            lines.append(f"<t:{entry.timestamp}:f>")
            lines.append(f"ID: `{entry.id}`")
            embed.add_field(name=label, value="\n".join(lines), inline=False)

        if not self.entries[start:start + ITEMS_PER_PAGE]:
            embed.add_field(name="No entries", value="No actions on this page.", inline=False)

        embed.set_footer(
            text=f"Page {self.page + 1}/{max(self.num_pages, 1)} • {len(self.entries)} total actions"
        )
        return embed

    async def update(self, interaction: discord.Interaction) -> None:
        _update_nav(self)
        embed = self._build_embed()
        if interaction.response.is_done():
            if self.message:
                await self.message.edit(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.page == 0:
            await interaction.response.defer()
            return
        self.page -= 1
        await self.update(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, row=1)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.page >= self.num_pages - 1:
            await interaction.response.defer()
            return
        self.page += 1
        await self.update(interaction)


def _disable_nav(view: ModerationHistoryView) -> None:
    for child in view.children:
        if isinstance(child, discord.ui.Button) and child.label in ("Back", "Next"):
            child.disabled = True


def _update_nav(view: ModerationHistoryView) -> None:
    for child in view.children:
        if isinstance(child, discord.ui.Button):
            if child.label == "Back":
                child.disabled = view.page == 0
            elif child.label == "Next":
                child.disabled = view.page >= view.num_pages - 1


# ── Quick-action components ───────────────────────────────────────────────────

class QuickActionModal(discord.ui.Modal):
    reason: discord.ui.TextInput = discord.ui.TextInput(
        label="Reason (optional)",
        required=False,
        max_length=512,
        placeholder="Enter a reason for this action...",
    )

    def __init__(self, suggestion: SuggestedAction, cog: Moderation, target: discord.Member):
        super().__init__(title=f"Confirm: {suggestion.label()}")
        self.suggestion = suggestion
        self.cog = cog
        self.target = target

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Cannot execute this action here.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        reason = self.reason.value or None

        try:
            at = self.suggestion.action_type
            if at == "tempmute":
                entry = await self.cog._execute_tempmute(
                    self.target, interaction.user, interaction.guild,
                    self.suggestion.duration or "4h", reason,
                )
            elif at == "kick":
                entry = await self.cog._execute_kick(
                    self.target, interaction.user, interaction.guild, reason)
            elif at == "ban":
                entry = await self.cog._execute_ban(
                    self.target, interaction.user, interaction.guild, reason)
            else:
                await interaction.followup.send(f"Unknown action type: {at}", ephemeral=True)
                return
        except discord.Forbidden:
            await interaction.followup.send("Missing permissions to execute that action.", ephemeral=True)
            return
        except discord.NotFound:
            await interaction.followup.send("User not found — they may have left the server.", ephemeral=True)
            return
        except ValueError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return

        insight = await self.cog._get_insight(self.target, interaction.guild)
        await self.cog._post_to_log_channel(interaction.guild, entry, insight, interaction.user, self.target)
        await self.cog._send_insight(interaction, self.target, insight)

        color = ACTION_COLORS.get(self.suggestion.action_type, discord.Color.red())
        embed = discord.Embed(
            title=f"{self.suggestion.label()} applied",
            description=f"{self.target.mention} has been {self.suggestion.action_type}d.",
            color=color,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


class QuickActionButton(discord.ui.Button):
    def __init__(self, suggestion: SuggestedAction, cog: Moderation, target: discord.Member):
        style_map = {
            "ban": discord.ButtonStyle.red,
            "kick": discord.ButtonStyle.primary,
            "tempmute": discord.ButtonStyle.primary,
        }
        super().__init__(
            label=suggestion.label(),
            style=style_map.get(suggestion.action_type, discord.ButtonStyle.secondary),
        )
        self.suggestion = suggestion
        self.cog = cog
        self.target = target

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.suggestion.action_type == "ban":
            embed = discord.Embed(
                title="Confirm Ban",
                description=(
                    f"Choose how far back to delete {self.target.mention}'s messages, "
                    f"then confirm the ban."
                ),
                color=discord.Color.dark_red(),
            )
            await interaction.response.send_message(
                embed=embed,
                view=_InsightBanView(self.suggestion, self.cog, self.target),
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(
            QuickActionModal(self.suggestion, self.cog, self.target)
        )


class MoreInfoButton(discord.ui.Button):
    def __init__(self, cog: Moderation, target: discord.Member):
        super().__init__(label="More Info", style=discord.ButtonStyle.secondary, emoji="🔍")
        self.cog = cog
        self.target = target

    async def callback(self, interaction: discord.Interaction) -> None:
        view = ModerationHistoryView(self.cog.bot, self.target, interaction.guild)
        await view.async_init()
        embed = view._build_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()


class ActionInsightView(discord.ui.View):
    def __init__(self, cog: Moderation, target: discord.Member, suggestions: list[SuggestedAction]):
        super().__init__(timeout=300)
        for suggestion in suggestions[:3]:
            self.add_item(QuickActionButton(suggestion, cog, target))
        self.add_item(MoreInfoButton(cog, target))


# ── Heuristics review queue — persistent DynamicItem buttons ─────────────────
# Each button encodes the target user_id in its custom_id so it survives restarts
# without needing a DB lookup. Guild context comes from interaction.guild_id.

async def _resolve_review(
    interaction: discord.Interaction,
    label: str,
    color: discord.Color,
) -> None:
    """Edit the review embed to show the resolution and strip all buttons."""
    if not interaction.message or not interaction.message.embeds:
        return
    embed = interaction.message.embeds[0]
    embed.color = color
    embed.set_footer(text=f"{label} • {interaction.user}")
    await interaction.message.edit(embed=embed, view=discord.ui.View())


class ReviewApproveItem(discord.ui.DynamicItem[discord.ui.Button],
                        template=r'review:approve:(?P<uid>\d+)'):
    def __init__(self, user_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label="Approve",
                style=discord.ButtonStyle.green,
                custom_id=f'review:approve:{user_id}',
                emoji='✅',
            )
        )
        self.user_id = user_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
    ) -> ReviewApproveItem:
        return cls(int(match['uid']))

    async def callback(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Must be used in a server.", ephemeral=True)
            return
        await interaction.response.defer()
        await _resolve_review(interaction, "Approved — no action taken", discord.Color.green())


class ReviewKickItem(discord.ui.DynamicItem[discord.ui.Button],
                     template=r'review:kick:(?P<uid>\d+)'):
    def __init__(self, user_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label="Kick",
                style=discord.ButtonStyle.primary,
                custom_id=f'review:kick:{user_id}',
                emoji='👢',
            )
        )
        self.user_id = user_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
    ) -> ReviewKickItem:
        return cls(int(match['uid']))

    async def callback(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Must be used in a server.", ephemeral=True)
            return
        if not interaction.user.guild_permissions.kick_members:
            await interaction.response.send_message("You don't have permission to kick.", ephemeral=True)
            return
        await interaction.response.defer()

        member = interaction.guild.get_member(self.user_id)
        if member is None:
            try:
                member = await interaction.guild.fetch_member(self.user_id)
            except discord.NotFound:
                member = None

        if member is None:
            await _resolve_review(interaction, "Kick attempted — member already left", discord.Color.greyple())
            return

        try:
            await member.kick(reason=f"Heuristics review: kicked by {interaction.user}")
        except discord.Forbidden:
            await interaction.followup.send("I don't have permission to kick that member.", ephemeral=True)
            return

        bot: KidneyBot = interaction.client  # type: ignore[assignment]
        entry = Schemas.ModLogEntry(
            id=str(uuid4()),
            guild_id=interaction.guild.id,
            user_id=self.user_id,
            moderator_id=interaction.user.id,
            action_type="kick",
            reason=f"Heuristics review queue (kicked by {interaction.user})",
            timestamp=int(time.time()),
        )
        await bot.database.mod_log.save(entry)
        bot.dispatch('modlog_entry', entry, interaction.guild)
        await _resolve_review(interaction, f"Kicked by {interaction.user}", discord.Color.red())


class ReviewBanItem(discord.ui.DynamicItem[discord.ui.Button],
                    template=r'review:ban:(?P<uid>\d+)'):
    def __init__(self, user_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label="Ban",
                style=discord.ButtonStyle.danger,
                custom_id=f'review:ban:{user_id}',
                emoji='🔨',
            )
        )
        self.user_id = user_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
    ) -> ReviewBanItem:
        return cls(int(match['uid']))

    async def callback(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Must be used in a server.", ephemeral=True)
            return
        embed = discord.Embed(
            title="Confirm Ban",
            description=(
                f"Choose how far back to delete <@{self.user_id}>'s messages, "
                f"then confirm the ban."
            ),
            color=discord.Color.dark_red(),
        )
        await interaction.response.send_message(
            embed=embed,
            view=_ReviewBanConfirmView(self.user_id, original_message=interaction.message),
            ephemeral=True,
        )


def make_review_view(user_id: int) -> discord.ui.View:
    """Build the three-button review view for a given target user_id."""
    view = discord.ui.View(timeout=None)
    view.add_item(ReviewApproveItem(user_id))
    view.add_item(ReviewKickItem(user_id))
    view.add_item(ReviewBanItem(user_id))
    return view


async def setup(bot: KidneyBot) -> None:
    pass
