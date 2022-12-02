# This cog creates all moderation commands.
# Copyright (C) 2022  Alec Jensen
# Full license at LICENSE.md

import discord
from discord.ext import commands
from discord import app_commands
from datetime import timedelta


time_convert = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
    "y": 31540000
}


class Moderation(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    async def permissionHierarchyCheck(self, user: discord.Member, target: discord.Member) -> bool:
        if target.top_role >= user.top_role:
            if user.guild.owner == user:
                return True
            else:
                return False
        elif target.top_role <= user.top_role:
            return True

    async def convert_time_to_seconds(self, time: str):
        try:
            return int(time[:-1]) * time_convert[time[-1]]
        except:
            return time

    @commands.Cog.listener()
    async def on_ready(self):
        print('Moderation cog loaded.')

    @app_commands.command(name='nickname', description="Change nicknames")
    @app_commands.default_permissions(manage_nicknames=True)
    async def nickname(self, interaction: discord.Interaction, user: discord.Member, *, newnick: str):
        if not await self.permissionHierarchyCheck(interaction.user, user):
            interaction.response.send_message("You cannot moderate users higher than you", ephemeral=True)
            return
        try:
            await user.edit(nick=newnick)
        except discord.errors.Forbidden:
            await interaction.response.send_message('Missing required permissions. Is the user above me?', ephemeral=True)
        else:
            await interaction.response.send_message('Nickname successfully changed!', ephemeral=True)

    @app_commands.command(name='purge', description="Purge messages")
    @app_commands.default_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, limit: int, user: discord.Member = None):
        if not await self.permissionHierarchyCheck(interaction.user, user):
            interaction.response.send_message("You cannot moderate users higher than you", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        msg = []
        if not user:
            await interaction.channel.purge(limit=limit, before=interaction.created_at)
        else:
            async for m in interaction.channel.history():
                if len(msg) == limit:
                    break
                if m.author == user:
                    msg.append(m)
            await interaction.channel.delete_messages(msg)
        await interaction.followup.send('Messages purged.')

    @app_commands.command(name='mute', description="Mute users")
    @app_commands.default_permissions(mute_members=True)
    async def mute(self, interaction: discord.Interaction, user: discord.Member, *, reason: str=None):
        if not await self.permissionHierarchyCheck(interaction.user, user):
            interaction.response.send_message("You cannot moderate users higher than you", ephemeral=True)
            return
        role = discord.utils.get(interaction.guild.roles, name="Muted")
        await user.add_roles(role, reason=f'by {interaction.user} for {reason}')
        await interaction.channel.send(f'{user.mention} was muted.', delete_after=10)

    @app_commands.command(name='unmute', description="Unmute users")
    @app_commands.default_permissions(mute_members=True)
    async def unmute(self, interaction: discord.Interaction, user: discord.Member):
        if not await self.permissionHierarchyCheck(interaction.user, user):
            interaction.response.send_message("You cannot moderate users higher than you", ephemeral=True)
            return
        # eventually, we will detect mutes from tempmutes
        await user.edit(timed_out_until=None)
        # await ctx.channel.send(f'{member.mention} was untempmuted.', delete_after=10)

        role = discord.utils.get(interaction.guild.roles, name="Muted")
        await user.remove_roles(role)
        await interaction.channel.send(f'{user.mention} was unmuted.', delete_after=10)

    @app_commands.command(name='tempmute', description="Timeout users")
    @app_commands.default_permissions(mute_members=True)
    async def tempmute(self, interaction: discord.Interaction, user: discord.Member, time: str, *, reason: str=None):
        if not await self.permissionHierarchyCheck(interaction.user, user):
            interaction.response.send_message("You cannot moderate users higher than you", ephemeral=True)
            return
        if await self.convert_time_to_seconds(time) > 1209600:
            await interaction.response.send_message('Timeouts can only be 2 weeks max!', ephemeral=True)
            return
        until = timedelta(seconds=await self.convert_time_to_seconds(time))
        await user.timeout(until, reason=reason)
        await interaction.response.send_message(f'{user.mention} was timed out for {time}.', ephemeral=True)
        await user.send(f"You have been muted in **{interaction.guild}** for *{time}*")


async def setup(bot):
    await bot.add_cog(Moderation(bot))
