# Main file, initializes the bot.
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import discord
from discord.ext import commands
import random
import asyncio
import os
import logging
import json
import datetime
import sys
import cogs.activeguard

now = datetime.datetime.now()
if not os.path.exists('logs'):
    os.makedirs('logs')
"""logging.basicConfig(filename=f'logs/{now.year}_{now.month}_{now.day}_{now.hour}-{now.minute}-{now.second}.txt',
                    filemode='a',
                    format="[%(asctime)s] [%(levelname)8s] --- %(message)s (%(name)s - %(filename)s:%(lineno)s)",
                    datefmt='%H:%M:%S',
                    level=logging.INFO)"""

class CustomFormatter(logging.Formatter):

    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format = "[%(asctime)s] [%(levelname)8s] --- %(message)s (%(name)s - %(filename)s:%(lineno)s)"

    FORMATS = {
        logging.DEBUG: grey + format + reset,
        logging.INFO: grey + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, '%H:%M:%S')
        return formatter.format(record)

logFormatter = CustomFormatter()
rootLogger = logging.getLogger()
rootLogger.setLevel(logging.INFO)

fileHandler = logging.FileHandler(f'logs/{now.year}_{now.month}_{now.day}_{now.hour}-{now.minute}-{now.second}.txt')
fileHandler.setFormatter(logFormatter)
rootLogger.addHandler(fileHandler)

consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logFormatter)
rootLogger.addHandler(consoleHandler)


class KidneyBotConfig:
    def __init__(self, conf):
        self.token = conf['token']
        self.dbstring = conf['dbstring']
        self.owner_id = int(conf['ownerid'])
        self.report_channel = int(conf['report_channel'])
        self.perspective_api_key = conf.get('perspective_api_key')


with open('config.json', 'r') as f:
    config = KidneyBotConfig(json.load(f))


class Bot(commands.Bot):

    def __init__(self, command_prefix, owner_id, intents):
        super().__init__(
            command_prefix=command_prefix,
            owner_id=owner_id,
            intents=intents
        )
        import motor.motor_asyncio
        client = motor.motor_asyncio.AsyncIOMotorClient(config.dbstring)
        self.database = client.data
        self.config = config

    async def setup_hook(self):
        await self.tree.sync()
        self.add_view(cogs.activeguard.ReportView())

    async def addcurrency(self, user: discord.User, value: int, location: str):
        n = await self.database.currency.count_documents({"userID": str(user.id)})
        if n == 1:
            doc = await self.database.currency.find_one({"userID": str(user.id)})
            if location == 'wallet':
                await self.database.currency.update_one({'userID': str(user.id)},
                                                        {'$set': {'wallet': str(int(doc['wallet']) + value)}})
            elif location == 'bank':
                await self.database.currency.update_one({'userID': str(user.id)},
                                                        {'$set': {'bank': str(int(doc['bank']) + value)}})
        else:
            wallet, bank = (0, 0)
            if location == 'wallet':
                wallet = value
            elif location == 'bank':
                bank = value
            await self.database.currency.insert_one({
                "userID": str(user.id),
                "wallet": str(wallet),
                "bank": str(bank),
                "inventory": []
            })
    
    async def log(self, guild: discord.Guild, actiontype: str, action: str, reason: str = None, user: discord.User = None, target: discord.User = None, message: discord.Message = None, color: discord.Color = None):
        doc = await self.database.automodsettings.find_one({'guild': guild.id})
        if doc is None:
            return
        if doc.get('log_channel') is None:
            return

        color = discord.Color.red() if color is None else color
        
        embed = discord.Embed(title=f'{actiontype}',
                              description=f'{action}\n**User:** {user.mention} ({user.id})' + 
                              (f"**Target:** {target.mention} ({target.id})" if target is not None else "") +
                              (f"\n**Reason:** {reason}\n" if reason is not None else "") +
                              (f'**Message:** ```{message.content}```' if message is not None else ''),
                              color=color)
        embed.set_footer(text=f'Automated logging by kidney bot')
        await self.get_channel(doc['log_channel']).send(embed=embed)


bot = Bot(command_prefix=commands.when_mentioned_or('kb.'),
            owner_id=config.owner_id,
            intents=discord.Intents.all()
            )

statuses = ["with the fate of the world", "minecraft"]


async def status():
    await bot.wait_until_ready()
    while not bot.is_closed():
        currentstatus = random.choice(statuses)
        await bot.change_presence(activity=discord.Game(name=currentstatus))
        await asyncio.sleep(10)


@bot.listen('on_ready')
async def on_ready():
    logging.info(f'We have logged in as {bot.user}')


@bot.listen('on_guild_join')
async def on_guild_join(guild):
    n = await bot.database.serverbans.count_documents({"id": str(guild.id)})
    if n > 0:
        doc = await bot.database.serverbans.find_one({"id": str(guild.id)})
        embed = discord.Embed(title=f"{guild} is banned.",
                              description=f"Your server *{guild}* is banned from using **{bot.user.name}**.",
                              color=discord.Color.red())
        embed.add_field(name=f"You can appeal by contacting __**{bot.get_user(766373301169160242)}**__.",
                        value="\u2800")
        embed.add_field(name="Reason", value=f"```{doc['reason']}```")
        embed.set_footer(text=bot.user, icon_url=bot.user.avatar)
        await guild.owner.send(embed=embed)
        await guild.leave()


@bot.listen('on_guild_remove')
async def on_guild_remove(guild):
    await bot.database.bans.remove_many({"serverID": str(guild.id)})
    await bot.database.prefixes.remove_many({"id": str(guild.id)})


@bot.command()
@commands.is_owner()
async def testLog(ctx, actiontype, action, reason, user: discord.User):
    await bot.log(ctx.guild, actiontype, action, reason, user)


@bot.command()
@commands.is_owner()
async def load(ctx, extension: str):
    try:
        os.rename(f'cogs/-{extension}.py', f'cogs/{extension}.py')
        await bot.load_extension(f'cogs.{extension}')
        await ctx.reply(f'Loaded cog {extension}')
        logging.info(f'{extension.capitalize()} cog loaded.')
    except Exception as e:
        await ctx.reply(f'Could not load cog {extension}\n`{e}`')


@bot.command()
@commands.is_owner()
async def unload(ctx, extension: str):
    try:
        await bot.unload_extension(f'cogs.{extension}')
        os.rename(f'cogs/{extension}.py', f'cogs/-{extension}.py')
        await ctx.reply(f'Unlodaded cog {extension}')
        logging.info(f'{extension.capitalize()} cog unloaded.')
    except Exception as e:
        await ctx.reply(f'Could not unload cog {extension}\n`{e}`')


@bot.command()
@commands.is_owner()
async def reload(ctx, extension: str):
    try:
        await bot.unload_extension(f'cogs.{extension}')
    except Exception as e:
        await ctx.reply(f'Could not unload cog {extension}\n`{e}`')
    try:
        await bot.load_extension(f'cogs.{extension}')
        await ctx.reply(f'Reloaded cog {extension}')
        logging.info(f'Reloaded cog {extension}')
    except Exception as e:
        await ctx.reply(f'Could not load cog {extension}\n`{e}`')


@bot.command()
@commands.is_owner()
async def say(ctx, *, text: str):
    try:
        await ctx.message.delete()
    except:
        pass
    await ctx.channel.send(text)


@bot.command()
@commands.is_owner()
async def reply(ctx, message: str, *, text: str):
    try:
        await ctx.message.delete()
    except:
        pass
    channel = ctx.channel
    message = await channel.fetch_message(int(message))
    await message.reply(text)


@bot.command()
@commands.is_owner()
async def react(ctx, message: str, reaction: str):
    try:
        await ctx.message.delete()
    except:
        pass
    channel = ctx.channel
    message = await channel.fetch_message(int(message))
    await message.add_reaction(reaction)


@bot.command()
@commands.is_owner()
async def announce(ctx, *, message: str):
    await ctx.reply(f'Sent global message\n```{message}```')
    ids = []
    for guild in bot.guilds:
        if int(guild.owner_id) not in ids:
            await guild.owner.send(
                f'Message from the dev!\n```{message}```(you are receiving this, because you own a server with this bot)')
            ids.append(int(guild.owner_id))


@bot.command()
@commands.is_owner()
async def raiseexception(ctx):
    raise Exception('artificial exception raised')


@bot.command()
@commands.is_owner()
async def serverban(ctx, guild: discord.Guild, *, text: str):
    n = await bot.database.serverbans.count_documents({"id": str(guild.id)})
    if n > 0:
        await ctx.response.send_message("Server already banned!", ephemeral=True)
        return
    doc = {
        "id": str(guild.id),
        "name": str(guild),
        "owner": str(guild.owner),
        "reason": str(text)
    }
    embed = discord.Embed(title=f"{guild} has been banned.",
                          description=f"Your server *{guild}* has been banned from using **{bot.user.name}**.",
                          color=discord.Color.red())
    embed.add_field(name=f"You can appeal by contacting __**{ctx.message.author}**__.", value="\u2800")
    embed.add_field(name="Reason", value=f"```{text}```")
    embed.set_footer(text=bot.user, icon_url=bot.user.avatar)
    await guild.owner.send(embed=embed)
    """serverbandic[guild.id] = {
        "name": str(guild),
        "owner": str(guild.owner),
        "reason": text
    }
    with open("serverbans.json", "w") as file:
        json.dump(serverbandic, file)"""
    await ctx.reply(
        f"Server *{guild}* has been permanently blacklisted from using **{bot.user.name}**")
    bot.database.serverbans.insert_one(doc)
    await guild.leave()


@bot.command()
@commands.is_owner()
async def serverunban(ctx, guild: str):
    n = await bot.database.serverbans.count_documents({"id": str(guild)})
    if n == 0:
        await ctx.reply("Server not banned!")
        return
    await bot.database.serverbans.delete_one({"id": str(guild)})
    await ctx.reply(f"Server *{guild}* has been unbanned from using **{bot.user.name}**")


@bot.command()
@commands.is_owner()
async def createinvite(ctx, guild: discord.Guild):
    inv = 'error'
    for i in guild.text_channels:
        try:
            inv = await i.create_invite(max_uses=1, reason='bot developer requested server invite.')
            break
        except:
            pass
    await ctx.reply(inv)


async def main():
    async with bot:
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                if not filename.startswith('-'):
                    await bot.load_extension(f'cogs.{filename[:-3]}')

        await bot.load_extension('jishaku')

        asyncio.create_task(status())

        await bot.start(config.token)


asyncio.run(main())
