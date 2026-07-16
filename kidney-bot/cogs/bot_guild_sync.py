# Bot guild sync — mirrors guild presence/metadata into Schemas.BotGuild so
# external services (e.g. the web dashboard's FastAPI backend) can determine
# which guilds the bot is in via a Mongo read, with zero coupling to the live
# gateway process.
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from utils.database import Schemas
from utils.kidney_bot import KidneyBot


class BotGuildSync(commands.Cog):
    def __init__(self, bot: KidneyBot) -> None:
        self.bot = bot

    async def _upsert(self, guild: discord.Guild) -> None:
        await self.bot.database.bot_guilds.save(Schemas.BotGuild(
            guild_id=guild.id,
            name=guild.name,
            icon=guild.icon.key if guild.icon else None,
            member_count=guild.member_count,
            owner_id=guild.owner_id,
        ))

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        for guild in self.bot.guilds:
            await self._upsert(guild)
        logging.info("Bot guild sync: refreshed %d guild(s).", len(self.bot.guilds))

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self._upsert(guild)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        await self.bot.database.bot_guilds.delete(guild.id)

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        await self._upsert(after)


async def setup(bot: KidneyBot) -> None:
    await bot.add_cog(BotGuildSync(bot))
