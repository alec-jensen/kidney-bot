import logging

import discord
from discord.ext import commands

from utils.kidney_bot import KidneyBot


class InviteTracking(commands.Cog):
    def __init__(self, bot: KidneyBot):
        self.bot: KidneyBot = bot

    @commands.Cog.listener()
    async def on_load(self):
        logging.info("Invite tracking cog loaded.")

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        pass


async def setup(bot: KidneyBot):
    await bot.add_cog(InviteTracking(bot))
