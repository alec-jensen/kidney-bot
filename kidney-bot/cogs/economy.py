# This cog creates all economy based commands
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import discord
from discord.ext import commands
from discord import app_commands
import random
import logging

from utils.database import Database
from utils.kidney_bot import KidneyBot
from utils.checks import is_bot_owner


class UserProfile:
    def __init__(self, bot: KidneyBot, database: Database, user: discord.User):
        self.bot: KidneyBot = bot
        self.database: Database = database
        self.user: discord.User = user

    async def async_init(self):
        await self.bot.add_currency(self.user, 0, 'wallet')

    async def wallet(self) -> int:
        doc = await self.database.currency.find_one({'userID': str(self.user.id)})
        return int(doc['wallet'])

    async def bank(self) -> int:
        doc = await self.database.currency.find_one({'userID': str(self.user.id)})
        return int(doc['bank'])

    async def inventory(self) -> list:
        doc = await self.database.currency.find_one({'userID': str(self.user.id)})
        return list(doc['inventory'])

    async def doc(self):
        return await self.database.currency.find_one({'userID': str(self.user.id)})

    async def add_currency(self, amount: int, location: str):
        location = location.lower()
        if location not in ['wallet', 'bank']:
            raise ValueError(
                f"Parameter \"location\" must be 'wallet' or 'bank' got: {location}")
        await self.bot.add_currency(self.user, amount, location)


class Economy(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info('Economy cog loaded.')

    @commands.command()
    @is_bot_owner()
    async def resetuser(self, ctx, user: discord.User):
        await self.bot.database.currency.delete_one({'userID': str(user.id)})
        await ctx.send('User removed successfully!')

    @commands.command()
    @is_bot_owner()
    async def addmoney(self, ctx, user: discord.User, amount: int):
        await self.bot.add_currency(user, amount, 'wallet')

    @app_commands.command(name="beg", description='Imagine being that beanless lol. 30 second cooldown.')
    @app_commands.checks.cooldown(1, 6, key=lambda i: i.user.id)
    async def beg(self, interaction: discord.Interaction):
        await interaction.response.defer()
        amount = random.randint(0, 100)
        await self.bot.add_currency(interaction.user, amount, 'wallet')
        await interaction.followup.send(f'You gained {amount} from begging!')

    @app_commands.command(name="balance", description='View your bean count')
    async def balance(self, interaction: discord.Interaction, user: discord.User = None):
        await interaction.response.defer()
        if not user:
            user = interaction.user
        profile = UserProfile(self.bot, self.bot.database, user)
        await profile.async_init()

        embed = discord.Embed(title=f"{user.name}'s balance", color=0x00ff00)
        embed.add_field(name="Wallet", value=f"{await profile.wallet()} beans", inline=False)
        embed.add_field(name="Bank", value=f"{await profile.bank()} beans", inline=False)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="deposit", description='Deposit beans')
    @app_commands.describe(amount="Numerical value, 'all', or 'half'")
    async def deposit(self, interaction: discord.Interaction, amount: str):
        await interaction.response.defer()
        profile = UserProfile(self.bot, self.bot.database, interaction.user)
        await profile.async_init()
        try:
            int(amount)
        except:
            if amount.lower() == 'all':
                amount = int(await profile.wallet())
            elif amount.lower() == 'half':
                amount = int(await profile.wallet()) // 2
            else:
                await interaction.followup.send('Value must be a number, "all", or "half"', ephemeral=True)
                return
        if int(amount) <= int(await profile.wallet()):
            await profile.add_currency(-int(amount), 'wallet')
            await profile.add_currency(int(amount), 'bank')
            await interaction.followup.send(f'Deposited {int(amount)} beans')
        else:
            await interaction.followup.send('You are trying to deposit more beans than you have!',
                                                    ephemeral=True)

    @app_commands.command(name="withdraw", description="Withdraw beans")
    @app_commands.describe(amount="Numerical value, 'all', or 'half'")
    async def withdraw(self, interaction: discord.Interaction, amount: str):
        await interaction.response.defer()
        profile = UserProfile(self.bot, self.bot.database, interaction.user)
        await profile.async_init()
        try:
            int(amount)
        except:
            if amount.lower() == 'all':
                amount = int(await profile.bank())
            elif amount.lower() == 'half':
                amount = int(await profile.bank()) // 2
            else:
                await interaction.followup.send('Value must be a number, "all", or "half"', ephemeral=True)
                return
        if int(amount) <= int(await profile.bank()):
            await profile.add_currency(int(amount), 'wallet')
            await profile.add_currency(-int(amount), 'bank')
            await interaction.followup.send(content=f'Withdrew {amount} beans')
        else:
            await interaction.followup.send('You are trying to withdraw more beans than you have!',
                                                    ephemeral=True)

    @app_commands.command(name='rob',
                          description='Rob someone of their beans and make them very mad. 30 second cooldown.')
    @app_commands.checks.cooldown(1, 30, key=lambda i: i.user.id)
    async def rob(self, interaction: discord.Interaction, user: discord.User):
        await interaction.response.defer()
        profile = UserProfile(self.bot, self.bot.database, interaction.user)
        await profile.async_init()

        target_profile = UserProfile(self.bot, self.bot.database, user)
        await target_profile.async_init()

        if int(await target_profile.wallet()) <= 11:
            await interaction.followup.send('They have no beans!', ephemeral=True)
        else:
            if int(await profile.wallet()) <= 50:
                await interaction.followup.send('You don\'t have enough money in your wallet!', ephemeral=True)
                return
            amount = random.randint(0, int(await profile.wallet() // 6))
            if amount < 2:
                await interaction.followup.send('You were caught! You pay 50 beans in fines.')
                await profile.add_currency(-50, 'wallet')
                return
            await target_profile.add_currency(-amount, 'wallet')
            await profile.add_currency(amount, 'wallet')
            await interaction.followup.send(f"Stole {amount} beans from {user.mention}")


async def setup(bot):
    await bot.add_cog(Economy(bot))
