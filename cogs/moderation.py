# This cog creates all moderation commands.
# Copyright (C) 2022  Alec Jensen
# Full license at LICENSE.md

import discord
from discord.ext import commands, tasks
import json
from datetime import datetime
import traceback
import asyncio
from datetime import timedelta
import math


def initdb():
    global dataDB
    import motor.motor_asyncio
    with open('dbstring.txt') as f:
        string = f.readlines()
    client = motor.motor_asyncio.AsyncIOMotorClient(string)
    dataDB = client.data


time_convert = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
    "y": 31540000
}


def convert_time_to_seconds(time):
    try:
        return int(time[:-1]) * time_convert[time[-1]]
    except:
        return time


class Moderation(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.ban_check.start()

    @commands.Cog.listener()
    async def on_ready(self):
        print('Moderation cog loaded.')

    @tasks.loop()
    async def ban_check(self):
        """ Tempban data structure
        {
        "userID": "",
        "unbanTime": "",
        "serverID": ""
        }"""
        # Code adapted from discord.py example.
        await self.bot.wait_until_ready()

        dataDB.bans.aggregate({"$sort": {"unbanTime": 1}})

        next_task = await dataDB.bans.find_one({})

        if next_task is None:
            return

        await discord.utils.sleep_until(datetime.fromtimestamp(int(float(next_task['unbanTime']))))

        # unban magic

        async for ban_entry in self.bot.get_guild(int(next_task["serverID"])).bans():
            banuser = ban_entry.user
            if str(banuser.id) == str(next_task['userID']):
                await self.bot.get_guild(int(next_task['serverID'])).unban(banuser,
                                                                           reason="KIDNEYBOT_AUTOMATED_ACTION - Temporary ban has expired")

        await dataDB.bans.delete_one(next_task)

    async def restartBanCheck(self):
        if self.ban_check.is_running():
            self.ban_check.restart()
        else:
            self.ban_check.start()

    @commands.command(aliases=['nick'], brief="Change nicknames", help="Change a user's nickname.")
    @commands.has_permissions(manage_nicknames=True)
    async def nickname(self, ctx, user: discord.Member, *, newnick):
        await ctx.message.delete()
        await user.edit(nick=newnick)

    @commands.command(brief="Purge messages", help="Purge any messages, or messages from a specific user.")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, limit, member: discord.Member = None):
        await ctx.message.delete()
        msg = []
        try:
            limit = int(limit)
        except:
            return await ctx.send("Please pass in an integer as limit")
        if not member:
            await ctx.channel.purge(limit=limit)
        async for m in ctx.channel.history():
            if len(msg) == limit:
                break
            if m.author == member:
                msg.append(m)
        await ctx.channel.delete_messages(msg)

    @commands.command(brief="Kick users", help="Kick users from the server.")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason=None):
        await ctx.message.delete()
        await member.kick(reason=f'by {ctx.author} for {reason}')
        await ctx.channel.send(f'**{member.display_name}** was kicked.', delete_after=10)

    @commands.command(brief="Ban users", help="Ban users from the server.")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason=None):
        await ctx.message.delete()
        await member.send(f"You were banned in {ctx.guild} for: {reason}. DM **{ctx.guild.owner}** to appeal.")
        await member.ban(reason=f'by {ctx.author} for {reason}')
        await ctx.channel.send(f'**{member.display_name}** was banned.', delete_after=10)

    @commands.command(brief="Mute users", help="Mute users in the server.")
    @commands.has_guild_permissions(mute_members=True)
    async def mute(self, ctx, member: discord.Member, *, reason=None):
        await ctx.message.delete()
        role = discord.utils.get(ctx.guild.roles, name="Muted")
        await member.add_roles(role, reason=f'by {ctx.author} for {reason}')
        await ctx.channel.send(f'{member.mention} was muted.', delete_after=10)

    @commands.command(brief="Unmute users", help="Unmute users in the server.")
    @commands.has_guild_permissions(mute_members=True)
    async def unmute(self, ctx, member: discord.Member):
        # eventually, we will detect mutes from tempmutes
        await ctx.message.delete()
        await member.edit(timed_out_until=None)
        # await ctx.channel.send(f'{member.mention} was untempmuted.', delete_after=10)

        role = discord.utils.get(ctx.guild.roles, name="Muted")
        await member.remove_roles(role)
        await ctx.channel.send(f'{member.mention} was unmuted.', delete_after=10)

    @commands.command(aliases=['timeout'], brief="Timeout users", help="Timeout server members. Max 2 weeks")
    @commands.has_guild_permissions(mute_members=True)
    async def tempmute(self, ctx, member: discord.Member, time, *, reason=None):
        await ctx.message.delete()
        if convert_time_to_seconds(time) > 1209600:
            await ctx.reply('Timeouts can only be 2 weeks max!')
            return
        until = timedelta(seconds=convert_time_to_seconds(time))
        await member.timeout(until, reason=reason)
        await ctx.channel.send(f'{member.mention} was timed out for {time}.', delete_after=10)
        await member.send(f"You have been muted in **{ctx.guild}** for *{time}*")

    @commands.command(brief="Tempban users", help="Temporarily ban server members.")
    @commands.has_permissions(ban_members=True)
    async def tempban(self, ctx, member: discord.Member, time, *, reason=None):
        await ctx.message.delete()
        await member.ban(reason=f'by {ctx.author} for {reason}')
        await dataDB.bans.insert_one({"userID": str(member.id),
                                      "unbanTime": str(datetime.now().timestamp() + convert_time_to_seconds(time)),
                                      "serverID": str(ctx.guild.id)})
        await ctx.channel.send(f'{member.mention} was banned for {time}.', delete_after=10)
        await member.send(f"You have been banned in **{ctx.guild}** for *{time}*")
        await restartBanCheck()

    @commands.command(brief="Untempban users", help="Remove temporary bans.")
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, userID):
        await ctx.message.delete()
        doc = await dataDB.bans.find_one({"userID": str(userID), "serverID": str(ctx.guild.id)})
        if doc is not None:
            await dataDB.bans.delete_one(doc)
            await restartBanCheck()
        async for ban_entry in self.bot.get_guild(int(ctx.guild.id)).bans():
            banuser = ban_entry.user
            if str(banuser.id) == str(userID):
                await self.bot.get_guild(int(ctx.guild.id)).unban(banuser,
                                                                  reason=f"KIDNEYBOT_USER_TRIGGERED - Ban removed by {ctx.author}")
                await ctx.channel.send(f'{banuser} was unbanned.', delete_after=10)

    @commands.command(brief="Change the prefix", help="Change the bots prefix in your server.")
    @commands.has_permissions(administrator=True)
    async def changeprefix(self, ctx, prefix):
        n = await dataDB.prefixes.count_documents({"id": str(ctx.guild.id)})
        if n > 0:
            cursor = await dataDB.prefixes.find_one({"id": str(ctx.guild.id)})
            await dataDB.prefixes.replace_one(cursor, {"id": str(ctx.guild.id), "prefix": str(prefix)})
        else:
            await dataDB.prefixes.insert_one({"id": str(ctx.guild.id), "prefix": str(prefix)})

        cursor = await dataDB.prefixes.find_one({"id": str(ctx.guild.id)})
        await ctx.message.reply(f'Prefix changed to `{cursor["prefix"]}`')


async def setup(bot):
    initdb()
    await bot.add_cog(Moderation(bot))
