# This cog creates all automod commands
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import logging

import discord
from discord import app_commands
from discord.ext import commands

from utils import checks
from utils.database import Schemas
from utils.kidney_bot import KidneyBot


class Automod(commands.Cog):

    def __init__(self, bot: KidneyBot):
        self.bot: KidneyBot = bot

    async def check_whitelist(self, member_or_channel: discord.Member | discord.TextChannel) -> bool:
        doc = await self.bot.database.automodsettings.get(member_or_channel.guild.id)
        if doc is None:
            return False
        return member_or_channel.id in (doc.whitelist or [])

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info('Automod cog loaded.')

    auto_mod = app_commands.Group(name='automod', description='Manage Automod settings',
                                  default_permissions=discord.Permissions(manage_guild=True), guild_only=True)

    @auto_mod.command(name='log', description='Set the log channel for automod')
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def automod_log(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        doc = await self.bot.database.automodsettings.get(interaction.guild.id) or \
              Schemas.AutoModSettings(guild_id=interaction.guild.id)
        doc.log_channel = channel.id
        await self.bot.database.automodsettings.save(doc)
        await interaction.followup.send(f'Log channel set to {channel.mention}', ephemeral=True)

    @auto_mod.command(name="whitelist", description="Whitelist a user or channel from automod")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    @checks.is_guild_owner()
    async def whitelist(self, interaction: discord.Interaction, state: bool = True,
                        user: discord.User | None = None, channel: discord.TextChannel | None = None):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        if user is None and channel is None:
            await interaction.followup.send('Invalid arguments. Please provide a user or channel.', ephemeral=True)
            return
        if user is not None and channel is not None:
            await interaction.followup.send('Invalid arguments. Please provide a user or channel, not both.', ephemeral=True)
            return

        user_or_channel = user if user is not None else channel
        if user_or_channel is None:
            return

        doc = await self.bot.database.automodsettings.get(interaction.guild.id) or \
              Schemas.AutoModSettings(guild_id=interaction.guild.id, whitelist=[])
        whitelist = doc.whitelist or []

        if state:
            if user_or_channel.id in whitelist:
                await interaction.followup.send(f'{user_or_channel.mention} is already whitelisted.', ephemeral=True)
                return
            whitelist.append(user_or_channel.id)
        else:
            if user_or_channel.id not in whitelist:
                await interaction.followup.send(f'{user_or_channel.mention} is not whitelisted.', ephemeral=True)
                return
            whitelist.remove(user_or_channel.id)

        doc.whitelist = whitelist
        await self.bot.database.automodsettings.save(doc)

        if state:
            await interaction.followup.send(f'{user_or_channel.mention} whitelisted.', ephemeral=True)
        else:
            await interaction.followup.send(f'{user_or_channel.mention} unwhitelisted.', ephemeral=True)


async def setup(bot: KidneyBot):
    await bot.add_cog(Automod(bot))
