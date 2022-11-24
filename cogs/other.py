# This cog creates all uncategorized commands
# Copyright (C) 2022  Alec Jensen
# Full license at LICENSE.md

import discord
from discord.ext import commands
from discord import  app_commands
import psutil


class Other(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print('Other cog loaded.')

    @app_commands.command(name='invite', description='Invite the bot to your own server')
    async def invite(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Invite the bot here! https://discord.com/api/oauth2/authorize?client_id=870379086487363605&permissions=8&scope=bot")

    @app_commands.command(name='devstats', description='View the bot\'s usage of resources. Really only useful for the dev.')
    async def devstats(self, interaction: discord.Interaction):
        await interaction.response.send_message(f'ping: **{round(self.bot.latency * 1000)} ms\r**cpu:** {psutil.cpu_percent()}%\r**ram:** {psutil.virtual_memory().percent}%\r**disk:** {psutil.disk_usage("/").percent}%**', ephemeral=True)

    @app_commands.command(name='ping', description='Get the current ping of the bot.')
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"PONG! Latency: {round(self.bot.latency * 1000)} milliseconds")

    @app_commands.command(name='info', description='View info about the bot.')
    async def info(self, interaction: discord.Interaction):
        embed = discord.Embed(title='Info', color=discord.Color.blue())
        embed.add_field(name='kidney bot is a simple all purpose discord bot',
                        value='[Support Server](https://discord.com/invite/TsuZCbz5KD) | [Invite Me!](https://discord.com/oauth2/authorize?client_id=870379086487363605&permissions=8&scope=bot) | [Website](https://kidneybot.tk) | [GitHub](https://github.com/alec-jensen/kidney-bot)',
                        inline=False)
        embed.set_footer(text=interaction.user.name, icon_url=interaction.user.avatar.url)
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Other(bot))
