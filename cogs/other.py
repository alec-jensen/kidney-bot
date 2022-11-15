# This cog creates all uncategorized commands
# Copyright (C) 2022  Alec Jensen
# Full license at LICENSE.md

import discord
from discord.ext import commands
import psutil


class Other(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print('Other cog loaded.')

    @commands.command(brief='Invite the bot', help='Invite the bot with this command.')
    async def invite(self, ctx):
        await ctx.message.reply(
            f"Invite the bot here! https://discord.com/api/oauth2/authorize?client_id=870379086487363605&permissions=8&scope=bot"
        )

    @commands.command(brief='View resource usage',
                      help='View the bots usage of resources. Really only useful for the dev.')
    async def devstats(self, ctx):
        await ctx.channel.send(
            f'ping: **{round(self.bot.latency * 1000)} ms\r**cpu:** {psutil.cpu_percent()}%\r**ram:** {psutil.virtual_memory().percent}%\r**disk:** {psutil.disk_usage("/").percent}%**')

    @commands.command(brief='Get the ping', help='Get the current ping of the bot.')
    async def ping(self, ctx):
        await ctx.send(f"PONG! Latency: {round(self.bot.latency * 1000)} milliseconds")

    @commands.command(brief='View bot info', help='View info about the bot.')
    async def info(self, ctx):
        await ctx.message.reply(
            'Check out the docs here: https://kidneybot.tk/\nJoin the support Discord here: https://discord.gg/TsuZCbz5KD\nDeveloper: `kidney bean#6938`')


async def setup(bot):
    await bot.add_cog(Other(bot))
