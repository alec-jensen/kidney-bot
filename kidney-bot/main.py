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
    channel = bot.get_channel(bot.config.user_count_channel_id)
    if channel is None:
        logging.warning("User count channel not found, not counting users.")
        return
    
    while not bot.is_closed():
        await channel.edit(name=f"Total Users: {len(bot.users)}")
        await asyncio.sleep(360)


@bot.listen('on_ready')
async def on_ready():
    logging.info(f"Kidney Bot {__version__}")
    logging.info(f"Ready in {(time.perf_counter_ns() - start) / 1e9} seconds.")
    logging.info(f"Logged in as {bot.user} ({bot.user.id})")


@bot.listen('on_guild_join')
async def on_guild_join(guild: discord.Guild):
    doc = await bot.database.serverbans.find_one({"id": guild.id})
    if doc is not None:
        embed = discord.Embed(title=f"{guild} is banned.",
                              description=f"Your server *{guild}* is banned from using **{bot.user.name}**.",
                              color=discord.Color.red())
        embed.add_field(name=f"You can appeal by contacting __**{bot.get_user(bot.config.owner_id).mention}**__.",
                        value="\u2800")
        embed.add_field(name="Reason", value=f"```{doc['reason']}```")
        embed.set_footer(text=bot.user, icon_url=bot.user.avatar)
        await guild.owner.send(embed=embed)
        await guild.leave()


@bot.command()
@bot.is_owner()
async def testLog(ctx, actiontype, action, reason, user: discord.User):
    """Internal command for testing the log function."""
    await bot.log(ctx.guild, actiontype, action, reason, user)


@bot.command()
@bot.is_owner()
async def load(ctx, extension: str):
    """Load a cog."""
    try:
        os.rename(f'cogs/-{extension}.py', f'cogs/{extension}.py')
        await bot.load_extension(f'cogs.{extension}')
        await ctx.reply(f'Loaded cog {extension}')
        logging.info(f'{extension.capitalize()} cog loaded.')
    except Exception as e:
        await ctx.reply(f'Could not load cog {extension}\n`{e}`')


@bot.command()
@bot.is_owner()
async def unload(ctx, extension: str):
    """Unload a cog."""
    try:
        await bot.unload_extension(f'cogs.{extension}')
        os.rename(f'cogs/{extension}.py', f'cogs/-{extension}.py')
        await ctx.reply(f'Unlodaded cog {extension}')
        logging.info(f'{extension.capitalize()} cog unloaded.')
    except Exception as e:
        await ctx.reply(f'Could not unload cog {extension}\n`{e}`')


@bot.command()
@bot.is_owner()
async def reload(ctx, extension: str):
    """Reload a cog."""
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
@bot.is_owner()
async def say(ctx, *, text: str):
    """Make the bot say something."""
    try:
        await ctx.message.delete()
    except:
        pass
    await ctx.channel.send(text)


@bot.command()
@bot.is_owner()
async def reply(ctx, message: str, *, text: str):
    """Make the bot reply to a message."""
    try:
        await ctx.message.delete()
    except:
        pass
    channel = ctx.channel
    message = await channel.fetch_message(int(message))
    await message.reply(text)


@bot.command()
@bot.is_owner()
async def react(ctx, message: str, reaction: str):
    """Make the bot react to a message."""
    try:
        await ctx.message.delete()
    except:
        pass
    channel = ctx.channel
    message = await channel.fetch_message(int(message))
    await message.add_reaction(reaction)


@bot.command()
@bot.is_owner()
async def announce(ctx, *, message: str):
    """Send a global message to all server owners."""
    await ctx.reply(f'Sent global message\n```{message}```')
    ids = []
    for guild in bot.guilds:
        if int(guild.owner_id) not in ids:
            await guild.owner.send(
                f'Message from the dev!\n```{message}```(you are receiving this, because you own a server with this bot)')
            ids.append(int(guild.owner_id))


@bot.command()
@bot.is_owner()
async def raiseexception(ctx):
    """Internal command for testing error handling."""
    raise Exception('artificial exception raised')


@bot.command()
@bot.is_owner()
async def serverban(ctx, guild: discord.Guild, *, text: str):
    """Ban a server from using the bot."""
    n = await bot.database.serverbans.count_documents({"id": str(guild.id)})
    if n > 0:
        await ctx.response.send_message("Server already banned!", ephemeral=True)
        return
    doc = {
        "id": guild.id,
        "name": guild,
        "owner": guild.owner,
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
@bot.is_owner()
async def serverunban(ctx, guild: str):
    """Unban a server from using the bot."""
    n = await bot.database.serverbans.count_documents({"id": guild})
    if n == 0:
        await ctx.reply("Server not banned!")
        return
    await bot.database.serverbans.delete_one({"id": guild})
    await ctx.reply(f"Server *{guild}* has been unbanned from using **{bot.user.name}**")


@bot.command()
@bot.is_owner()
async def createinvite(ctx, guild: discord.Guild):
    """Create an invite to a server."""
    invite = None
    for channel in guild.text_channels:
        try:
            invite = await channel.create_invite(max_uses=1, reason='bot developer requested server invite.')
            break
        except:
            pass

    if invite is None:
        return await ctx.reply("Could not create invite.")

    await ctx.reply(invite)


@bot.command()
@bot.is_owner()
async def reloadconfig(ctx):
    """Reload the config file."""
    try:
        bot.config.reload()
    except Exception as e:
        await ctx.reply(f"Could not reload config file.\n`{e}`")
        return

    await ctx.reply("Reloaded config file.")

@bot.command()
@bot.is_owner()
async def guild_debug_info(ctx: commands.Context, guild: discord.Guild = None):
    message = await ctx.send("Generating debug report...")
    if guild is None:
        guild = ctx.guild

    embed = discord.Embed(title=f"Debug report for {guild}({guild.id})", color=discord.Color.blurple())
    embed.add_field(name=guild.name, value=f"""**Owner:** {guild.owner}({guild.owner_id})
                    **Created:** <t:{guild.created_at.timestamp}>
                    **Members:** {guild.member_count}""")
    
    possible_issues = []

    # Check if bot has the correct permissions
    permissions = guild.me.guild_permissions
    missing_permissions = []

    if not permissions.administrator:
        missing_permissions.append("Administrator")
    if not permissions.manage_messages:
        missing_permissions.append("Manage Messages")
    if not permissions.kick_members:
        missing_permissions.append("Kick Members")
    if not permissions.ban_members:
        missing_permissions.append("Ban Members")
    if not permissions.manage_nicknames:
        missing_permissions.append("Manage Nicknames")
    
    if len(missing_permissions) > 0:
        possible_issues.append(f"Missing permissions: {', '.join(missing_permissions)}")

    # Check if bot's role is above normal members
    top_role_pos = len(guild.me.roles) - 1

    for i, role in enumerate(guild.roles):
        if i < top_role_pos: pass

        role_perms = role.permissions

        if not role_perms.manage_messages or not role_perms.manage_nicknames:
            possible_issues.append(f"Role may not be above normal members. Found {role.mention} above me.")

    # TODO: check database for issues

    if len(possible_issues) == 0:
        embed.add_field(name="No issues found!", value="")
    else:
        embed.add_field(name="Possible issues:", value="\n".join(possible_issues))

    embed.set_footer(text=f"Debug report for {guild.name}", icon_url=guild.icon.url)

    await message.edit(content="", embed=embed)


async def main():
    async with bot:
        for filename in os.listdir(os.path.join(os.path.dirname(__file__), "cogs")):
            if filename.endswith('.py'):
                if not filename.startswith('-'):
                    await bot.load_extension(f'cogs.{filename[:-3]}')

        # Why does the status stop working after a while?
        asyncio.create_task(status())

        if bot.config.user_count_channel_id is not None:
            asyncio.create_task(user_count())
        else:
            logging.warning("No user count channel set, not counting users.")

        await bot.start(bot.config.token)

if __name__ == '__main__':
    asyncio.run(main())
