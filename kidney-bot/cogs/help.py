# Interactive help system with multi-level navigation.
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from utils.command_catalog import CATEGORIES
from utils.kidney_bot import KidneyBot

# ── Category select options (built once at module level) ──────────────────────

_CATEGORY_OPTIONS: list[discord.SelectOption] = [
    discord.SelectOption(
        label=cat["name"],
        value=key,
        description=cat["description"][:100],
        emoji=cat["emoji"],
    )
    for key, cat in CATEGORIES.items()
]


# ── Embed builders ────────────────────────────────────────────────────────────

def _main_embed() -> discord.Embed:
    embed = discord.Embed(
        title="📖 kidney bot — Help",
        description=(
            "kidney bot is a multi-purpose Discord bot for moderation, music, "
            "economy, fun, and anti-raid protection.\n\n"
            "**Select a category below to browse commands.**"
        ),
        color=discord.Color.blurple(),
    )
    for cat in CATEGORIES.values():
        n = len(cat["commands"])
        embed.add_field(
            name=f"{cat['emoji']} {cat['name']}",
            value=f"*{n} command{'s' if n != 1 else ''}*",
            inline=True,
        )
    embed.set_footer(text="<required>  [optional]  •  All commands use Discord slash commands (/)")
    return embed


def _category_embed(cat_key: str) -> discord.Embed:
    cat = CATEGORIES[cat_key]
    lines: list[str] = [cat["description"], ""]
    for cmd in cat["commands"]:
        lines.append(f"**`{cmd['name']}`** — {cmd['brief']}")
    description = "\n".join(lines)
    if len(description) > 4000:
        description = description[:3990] + "\n…"
    embed = discord.Embed(
        title=f"{cat['emoji']} {cat['name']}",
        description=description,
        color=discord.Color.blurple(),
    )
    embed.set_footer(text="Select a command below for detailed usage info")
    return embed


def _command_embed(cat_key: str, cmd_name: str) -> discord.Embed:
    cat = CATEGORIES[cat_key]
    cmd = next((c for c in cat["commands"] if c["name"] == cmd_name), None)
    if cmd is None:
        return discord.Embed(title="Command not found", color=discord.Color.red())

    embed = discord.Embed(
        title=cmd["name"],
        description=cmd["description"],
        color=discord.Color.blurple(),
    )

    embed.add_field(name="📋 Usage", value=f"`{cmd['usage']}`", inline=False)

    if cmd["params"]:
        param_lines: list[str] = []
        for p in cmd["params"]:
            req = "required" if p["required"] else "optional"
            param_lines.append(f"**`{p['name']}`** *({p['type']}, {req})*\n{p['desc']}")
        value = "\n\n".join(param_lines)
        if len(value) > 1020:
            value = value[:1017] + "…"
        embed.add_field(name="🔧 Parameters", value=value, inline=False)
    else:
        embed.add_field(name="🔧 Parameters", value="None — this command takes no arguments.", inline=False)

    if cmd["perm"]:
        embed.add_field(name="🔒 Required Permission", value=cmd["perm"], inline=True)

    if cmd["examples"]:
        embed.add_field(
            name="💡 Examples",
            value="\n".join(f"`{ex}`" for ex in cmd["examples"]),
            inline=False,
        )

    embed.set_footer(text=f"{cat['emoji']} {cat['name']}  •  <required>  [optional]")
    return embed


# ── UI components ─────────────────────────────────────────────────────────────

class _CommandSelect(discord.ui.Select):
    """Dynamic select listing all commands in a given category."""

    def __init__(self, cat_key: str) -> None:
        cat = CATEGORIES[cat_key]
        options = [
            discord.SelectOption(
                label=cmd["name"].lstrip("/")[:100],
                value=cmd["name"],
                description=cmd["brief"][:100],
            )
            for cmd in cat["commands"][:25]  # Discord limit
        ]
        super().__init__(
            placeholder=f"Select a command from {cat['name']}…",
            options=options,
            row=0,
        )
        self.cat_key = cat_key

    async def callback(self, interaction: discord.Interaction) -> None:
        cmd_name = self.values[0]
        embed = _command_embed(self.cat_key, cmd_name)
        view = _CommandView(self.cat_key)
        await interaction.response.edit_message(embed=embed, view=view)


class HelpMainView(discord.ui.View):
    """Root help view — shows the category select menu."""

    def __init__(self) -> None:
        super().__init__(timeout=300)

    @discord.ui.select(
        placeholder="Choose a category…",
        options=_CATEGORY_OPTIONS,
        row=0,
    )
    async def category_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        cat_key = select.values[0]
        embed = _category_embed(cat_key)
        view = _CategoryView(cat_key)
        await interaction.response.edit_message(embed=embed, view=view)


class _CategoryView(discord.ui.View):
    """Category view — shows a command select and a Home button."""

    def __init__(self, cat_key: str) -> None:
        super().__init__(timeout=300)
        self.cat_key = cat_key
        self.add_item(_CommandSelect(cat_key))

    @discord.ui.button(label="Home", style=discord.ButtonStyle.secondary, emoji="🏠", row=1)
    async def home(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(embed=_main_embed(), view=HelpMainView())


class _CommandView(discord.ui.View):
    """Command detail view — shows Back and Home buttons."""

    def __init__(self, cat_key: str) -> None:
        super().__init__(timeout=300)
        self.cat_key = cat_key

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="⬅️", row=0)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=_category_embed(self.cat_key),
            view=_CategoryView(self.cat_key),
        )

    @discord.ui.button(label="Home", style=discord.ButtonStyle.secondary, emoji="🏠", row=0)
    async def home(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(embed=_main_embed(), view=HelpMainView())


# ── Cog ───────────────────────────────────────────────────────────────────────

class Help(commands.Cog):
    def __init__(self, bot: KidneyBot) -> None:
        self.bot = bot

    @app_commands.command(name="help", description="Browse all commands and learn how to use them.")
    async def help_command(self, interaction: discord.Interaction) -> None:
        embed = _main_embed()
        view = HelpMainView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: KidneyBot) -> None:
    await bot.add_cog(Help(bot))
