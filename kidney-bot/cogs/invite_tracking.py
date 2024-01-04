import discord
from discord.ext import commands
import logging

from utils.kidney_bot import KidneyBot
from utils.database import Schemas


class InviteTracking(commands.Cog):
    def __init__(self, bot):
        self.bot: KidneyBot = bot

    @commands.Cog.listener()
    async def on_load(self):
        logging.info("Invite tracking cog loaded.")

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        pass


async def setup(bot):
    await bot.add_cog(InviteTracking(bot))
