# Main file, initializes the bot.
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import discord
from discord.ext import commands
import random
import asyncio
import os
import logging
import datetime
import time

from _version import __version__
from utils.kidney_bot import KidneyBot
from utils.log_formatter import LogFormatter, LogFileFormatter

start = time.perf_counter_ns()

# Logging configuration

now = datetime.datetime.now()
if not os.path.exists('logs'):
    os.makedirs('logs')

logFormatter = LogFormatter()
rootLogger = logging.getLogger()
rootLogger.setLevel(logging.INFO)

consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logFormatter)
rootLogger.addHandler(consoleHandler)

logFileFormatter = LogFileFormatter()
fileHandler = logging.FileHandler(
    f'logs/{now.year}_{now.month}_{now.day}_{now.hour}-{now.minute}-{now.second}.log')
fileHandler.setFormatter(logFileFormatter)
rootLogger.addHandler(fileHandler)

bot: KidneyBot = KidneyBot(
    command_prefix=commands.when_mentioned_or('kb.'),
    intents=discord.Intents.all()
)

statuses: list[discord.Game] = [discord.Game("with the fate of the world"), discord.Game("minecraft"), discord.Game("with <users> users"),
                                discord.Streaming(
                                    name="<servers> servers", url="https://kidneybot.alecj.tk"), discord.Game("/rockpaperscissors"),
                                discord.Game("counting to infinity... twice"), discord.Game("attempting to break the sound barrier... of silence")]


async def status():
    await bot.wait_until_ready()
    while not bot.is_closed():
        current_status: discord.Game = random.choice(statuses)
        current_status.name = current_status.name.replace("<users>", str(len(bot.users)))\
            .replace("<servers>", str(len(bot.guilds)))
        await bot.change_presence(activity=current_status)

        await asyncio.sleep(16)

async def user_count():
    await bot.wait_until_ready()
    while not bot.is_closed():
        await bot.get_channel(bot.config.user_count_channel).edit(name=f"Total Users: {len(bot.users)}")
        await asyncio.sleep(360)


@bot.listen('on_ready')
async def on_ready():
    logging.info(f"Kidney Bot {__version__}")
    logging.info(f"Ready in {(time.perf_counter_ns() - start) / 1e9} seconds.")
    logging.info(f"Logged in as {bot.user} ({bot.user.id})")


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
        return
    
    try:
        await bot.load_extension(f'cogs.{extension}')
    except Exception as e:
        await ctx.reply(f'Could not load cog {extension}\n`{e}`')
        return

    await ctx.reply(f'Reloaded cog {extension}')
    logging.info(f'Reloaded cog {extension}')


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
    embed.add_field(
        name=f"You can appeal by contacting __**{ctx.message.author}**__.", value="\u2800")
    embed.add_field(name="Reason", value=f"```{text}```")
    embed.set_footer(text=bot.user, icon_url=bot.user.avatar)
    await guild.owner.send(embed=embed)
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
        for filename in os.listdir(os.path.join(os.path.dirname(__file__), "cogs")):
            if filename.endswith('.py'):
                if not filename.startswith('-'):
                    await bot.load_extension(f'cogs.{filename[:-3]}')

        await bot.load_extension('jishaku')

        asyncio.create_task(status())
        
        if bot.config.user_count_channel is not None:
            asyncio.create_task(user_count())
        else:
            logging.warning("No user count channel set, not counting users.")

        await bot.start(bot.config.token)

if __name__ == '__main__':
    asyncio.run(main())
