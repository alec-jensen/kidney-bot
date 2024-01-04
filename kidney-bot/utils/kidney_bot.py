# Bot class
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import discord
from discord.ext import commands
import logging

from utils.config import Config
from utils.database import Database, Schemas
from cogs import active_guard


class KidneyBot(commands.Bot):

    def __init__(self, command_prefix, intents):
        self.config: Config = Config()
        super().__init__(
            command_prefix=command_prefix,
            owner_id=self.config.owner_id,
            intents=intents
        )

        self.database: Database = Database(self.config.dbstring)

    async def setup_hook(self):
        await self.tree.sync()
        self.add_view(active_guard.ReportView())

    """Add currency to a user's wallet or bank."""
    async def add_currency(self, user: discord.User, value: int, location: str) -> None:
        doc: Schemas.Currency = await self.database.currency.find_one({"userID": str(user.id)}, Schemas.Currency)
        if doc is not None:
            if location == 'wallet':
                await self.database.currency.update_one({'userID': str(user.id)},
                                                        {'$set': {'wallet': str(int(doc.wallet) + value)}})
            elif location == 'bank':
                await self.database.currency.update_one({'userID': str(user.id)},
                                                        {'$set': {'bank': str(int(doc.bank) + value)}})
        else:
            wallet, bank = (0, 0)
            if location == 'wallet':
                wallet = value
            elif location == 'bank':
                bank = value

            document: Schemas.Currency = Schemas.Currency(
                userID=str(user.id),
                wallet=str(wallet),
                bank=str(bank)
            )

            await self.database.currency.insert_one(document)

    """Log an action to the configured log channel for a guild."""
    async def log(self, guild: discord.Guild, actiontype: str, action: str, reason: str, user: discord.User,
                  target: discord.User = None, message: discord.Message = None, color: discord.Color = None) -> discord.Message:
        doc = await self.database.automodsettings.find_one({'guild': guild.id})
        if doc is None:
            return
        if doc.get('log_channel') is None:
            return

        color = discord.Color.red() if color is None else color

        embed = discord.Embed(title=f'{actiontype}',
                              description=f'{action}\n**User:** {user.mention} ({user.id})\n' +
                              (f"**Target:** {target.mention} ({target.id})" if target is not None else "") +
                              (f"\n**Reason:** {reason}\n" if reason is not None else "") +
                              (f'**Message:** ```{message.content}```' if message is not None else ''),
                              color=color)
        embed.set_footer(text=f'Automated logging by kidney bot')
        return await self.get_channel(doc['log_channel']).send(embed=embed)

    # Decorators

    """
    Check if the user is the owner of the bot.
    This is different from the is_owner() check in
    discord.py because it works after config reloads.
    """

    def is_owner(self) -> commands.check:
        async def predicate(ctx: commands.Context):
            return ctx.author.id == self.config.owner_id
        return commands.check(predicate)
