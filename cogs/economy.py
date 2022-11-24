# This cog creates all economy based commands
# Copyright (C) 2022  Alec Jensen
# Full license at LICENSE.md

import discord
from discord.ext import commands
from discord import app_commands
import random

""" currency data format:
{
    "userID": "",
    "wallet": "",
    "bank": "",
    "inventory": []
}
"""


class Economy(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    async def initUser(self, user):
        await self.bot.addcurrency(user, 0, 'wallet')

    @commands.Cog.listener()
    async def on_ready(self):
        print('Economy cog loaded.')

    @commands.command()
    @commands.is_owner()
    async def resetuser(self, ctx, user: discord.User):
        await self.bot.database.currency.delete_one({'userID': str(user.id)})
        await ctx.send('User removed successfully!')

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
        await self.initUser(user)
        doc = await self.bot.database.currency.find_one({'userID': str(user.id)})
        await interaction.response.send_message(
            f"*{user.name}'s* balance:\n**Wallet: **{doc['wallet']} beans\n**Bank: **{doc['bank']} beans")

    @app_commands.command(name="deposit", description='Deposit beans')
    async def deposit(self, interaction: discord.Interaction, amount: str):
        await self.initUser(interaction.user)
        doc = await self.bot.database.currency.find_one({'userID': str(interaction.user.id)})
        try:
            int(amount)
        except:
            if amount.lower() == 'all':
                amount = int(doc['wallet'])
            elif amount.lower() == 'half':
                amount = int(doc['wallet']) // 2
            else:
                await interaction.response.send_message('Value must be a number, "all", or "half"', ephemeral=True)
                return
        if int(amount) <= int(doc['wallet']):
            await self.bot.addcurrency(interaction.user, -int(amount), 'wallet')
            await self.bot.addcurrency(interaction.user, int(amount), 'bank')
            await interaction.response.send_message(f'Deposited {int(amount)} beans')
        else:
            await interaction.response.send_message('You are trying to deposit more beans than you have!', ephemeral=True)

    @app_commands.command(name="withdraw", description="Withdraw beans")
    async def withdraw(self, interaction: discord.Interaction, amount: str):
        await self.initUser(interaction.user)
        doc = await self.bot.database.currency.find_one({'userID': str(interaction.user.id)})
        try:
            int(amount)
        except:
            if amount.lower() == 'all':
                amount = int(doc['bank'])
            elif amount.lower() == 'half':
                amount = int(doc['bank']) // 2
            else:
                await interaction.response.send_message('Value must be a number, "all", or "half"', ephemeral=True)
                return
        if int(amount) <= int(doc['bank']):
            await self.bot.addcurrency(interaction.user, int(amount), 'wallet')
            await self.bot.addcurrency(interaction.user, -int(amount), 'bank')
            await interaction.response.send_message(f'Withdrew {amount} beans')
        else:
            await interaction.response.send_message('You are trying to withdraw more beans than you have!', ephemeral=True)

    @app_commands.command(name='rob', description='Rob someone of their beans and make then very mad. 30 second cooldown.')
    @app_commands.checks.cooldown(1, 30, key=lambda i: i.user.id)
    async def rob(self, interaction: discord.Interaction, user: discord.User):
        await self.initUser(interaction.user)
        targetDoc = await self.bot.database.currency.find_one({'userID': str(user.id)})
        if int(targetDoc['wallet']) <= 11:
            await interaction.response.send_message('They have no beans!', ephemeral=True)
        else:
            doc = await self.bot.database.currency.find_one({'userID': str(interaction.user.id)})
            if int(doc['wallet']) <= 50:
                await interaction.response.send_message('You don\'t have enough money!', ephemeral=True)
                return
            amount = random.randint(0, int(int(doc['wallet']) / 6))
            if amount < 2:
                await interaction.response.send_message('You were caught! You pay 50 beans in fines.')
                await self.bot.addcurrency(interaction.user, -50, 'wallet')
                return
            await self.bot.addcurrency(user, -amount, 'wallet')
            await self.bot.addcurrency(interaction.user, amount, 'wallet')
            await interaction.response.send_message(f"Stole {amount} beans from {user.mention}")


async def setup(bot):
    await bot.add_cog(Economy(bot))
