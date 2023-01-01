# This cog creates all economy based commands
# Copyright (C) 2022  Alec Jensen
# Full license at LICENSE.md
import asyncio

import discord
from discord.ext import commands
from discord import app_commands
import random
import logging

""" currency data format:
{
    "userID": "",
    "wallet": "",
    "bank": "",
    "inventory": []
}
"""


class UserProfile:
    def __init__(self, bot, database, user: discord.User):
        self.bot = bot
        self.database = database
        self.user = user

    async def ainit(self):
        await self.bot.addcurrency(self.user, 0, 'wallet')

    async def wallet(self) -> int:
        return int(await self.database.currency.find_one({'userID': str(self.user.id)})['wallet'])

    async def bank(self) -> int:
        return int(await self.database.currency.find_one({'userID': str(self.user.id)})['bank'])

    async def inventory(self) -> list:
        return list(await self.database.currency.find_one({'userID': str(self.user.id)})['inventory'])

    async def doc(self):
        return await self.database.currency.find_one({'userID': str(self.user.id)})

    async def addcurrency(self, amount: int, location: str):
        location = location.lower()
        if location not in ['wallet', 'bank']:
            raise ValueError(f"Parameter \"location\" must be 'wallet' or 'bank' got: {location}")
        await self.bot.addcurrency(self.user, amount, location)


class Economy(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info('Economy cog loaded.')

    @commands.command()
    @commands.is_owner()
    async def resetuser(self, ctx, user: discord.User):
        await self.bot.database.currency.delete_one({'userID': str(user.id)})
        await ctx.send('User removed successfully!')

    @commands.command()
    @commands.is_owner()
    async def addmoney(self, ctx, user: discord.User, amount: int):
        await self.bot.addcurrency(user, amount, 'wallet')

    @app_commands.command(name="beg", description='Imagine being that beanless lol. 30 second cooldown.')
    @app_commands.checks.cooldown(1, 6, key=lambda i: i.user.id)
    async def beg(self, interaction: discord.Interaction):
        amount = random.randint(0, 100)
        await self.bot.addcurrency(interaction.user, amount, 'wallet')
        await interaction.response.send_message(f'You gained {amount} from begging!')

    @app_commands.command(name="balance", description='View your bean count')
    async def balance(self, interaction: discord.Interaction, user: discord.User = None):
        if not user:
            user = interaction.user
        profile = UserProfile(self.bot, self.bot.database, user)
        await profile.ainit()
        await interaction.response.send_message(
            f"*{user.name}'s* balance:\n**Wallet: **{await profile.wallet()} beans\n**Bank: **{await profile.bank()} beans")

    @app_commands.command(name="deposit", description='Deposit beans')
    async def deposit(self, interaction: discord.Interaction, amount: str):
        profile = UserProfile(self.bot, self.bot.database, interaction.user)
        await profile.ainit()
        try:
            int(amount)
        except:
            if amount.lower() == 'all':
                amount = int(await profile.wallet())
            elif amount.lower() == 'half':
                amount = int(await profile.wallet()) // 2
            else:
                await interaction.response.send_message('Value must be a number, "all", or "half"', ephemeral=True)
                return
        if int(amount) <= int(await profile.wallet()):
            await profile.addcurrency(-int(amount), 'wallet')
            await profile.addcurrency(int(amount), 'bank')
            await interaction.response.send_message(f'Deposited {int(amount)} beans')
        else:
            await interaction.response.send_message('You are trying to deposit more beans than you have!',
                                                    ephemeral=True)

    @app_commands.command(name="withdraw", description="Withdraw beans")
    async def withdraw(self, interaction: discord.Interaction, amount: str):
        profile = UserProfile(self.bot, self.bot.database, interaction.user)
        await profile.ainit()
        try:
            int(amount)
        except:
            if amount.lower() == 'all':
                amount = int(await profile.bank())
            elif amount.lower() == 'half':
                amount = int(await profile.bank()) // 2
            else:
                await interaction.response.send_message('Value must be a number, "all", or "half"', ephemeral=True)
                return
        if int(amount) <= int(await profile.bank()):
            await profile.addcurrency(int(amount), 'wallet')
            await profile.addcurrency(-int(amount), 'bank')
            await interaction.response.send_message(f'Withdrew {amount} beans')
        else:
            await interaction.response.send_message('You are trying to withdraw more beans than you have!',
                                                    ephemeral=True)

    @app_commands.command(name='rob',
                          description='Rob someone of their beans and make then very mad. 30 second cooldown.')
    @app_commands.checks.cooldown(1, 30, key=lambda i: i.user.id)
    async def rob(self, interaction: discord.Interaction, user: discord.User):
        profile = UserProfile(self.bot, self.bot.database, interaction.user)
        await profile.ainit()
        tProfile = UserProfile(self.bot, self.bot.database, user)
        await tProfile.ainit()
        if int(await tProfile.wallet()) <= 11:
            await interaction.response.send_message('They have no beans!', ephemeral=True)
        else:
            if int(await profile.wallet()) <= 50:
                await interaction.response.send_message('You don\'t have enough money in your wallet!', ephemeral=True)
                return
            amount = random.randint(0, int(await profile.wallet() // 6))
            if amount < 2:
                await interaction.response.send_message('You were caught! You pay 50 beans in fines.')
                await profile.addcurrency(-50, 'wallet')
                return
            await tProfile.addcurrency(-amount, 'wallet')
            await profile.addcurrency(amount, 'wallet')
            await interaction.response.send_message(f"Stole {amount} beans from {user.mention}")



async def setup(bot):
    await bot.add_cog(Economy(bot))
