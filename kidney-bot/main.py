# Main file, initializes the bot.
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import aiohttp
import discord
from discord.ext import commands
import random
import asyncio
import os
import logging
import datetime
import time
import regex as re
import traceback
import toml

from utils.kidney_bot import KidneyBot
from utils.log_formatter import LogFormatter, LogFileFormatter
from utils.checks import is_bot_owner
from utils.database import Schemas, ServerBansDocument, AutoRoleSettingsDocument

time_start = time.perf_counter_ns()

# Logging configuration

now = datetime.datetime.now()
if not os.path.exists("logs"):
    os.makedirs("logs")

logFormatter = LogFormatter()
rootLogger = logging.getLogger()
rootLogger.setLevel(logging.INFO)

consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logFormatter)
rootLogger.addHandler(consoleHandler)

logFileFormatter = LogFileFormatter()
fileHandler = logging.FileHandler(
    f"logs/{now.year}_{now.month}_{now.day}_{now.hour}-{now.minute}-{now.second}.log"
)
fileHandler.setFormatter(logFileFormatter)
rootLogger.addHandler(fileHandler)

bot: KidneyBot = KidneyBot(intents=discord.Intents.all())

statuses: list[discord.Game | discord.Streaming] = [
    discord.Game("with the fate of the world"),
    discord.Game("minecraft"),
    discord.Game("with <users> users"),
    discord.Streaming(name="<servers> servers", url="https://kidneybot.alecj.tk"),
    discord.Game("/rockpaperscissors"),
    discord.Game("counting to infinity... twice"),
    discord.Game("attempting to break the sound barrier... of silence"),
]

previous_statuses: list[discord.Game | discord.Streaming] = []


async def status():
    await bot.wait_until_ready()
    while not bot.is_closed():
        current_status: discord.Game = random.choice(statuses)  # type: ignore
        while current_status in previous_statuses:
            current_status = random.choice(statuses)  # type: ignore

        previous_statuses.append(current_status)

        current_status.name = current_status.name.replace(
            "<users>", str(len(bot.users))
        ).replace("<servers>", str(len(bot.guilds)))
        await bot.change_presence(activity=current_status)

        if len(previous_statuses) > 3:
            previous_statuses.pop(0)

        await asyncio.sleep(16)


async def user_count():
    await bot.wait_until_ready()
    channel = bot.get_channel(bot.config.user_count_channel_id)  # type: ignore
    if channel is None:
        logging.warning("User count channel not found, not counting users.")
        return

    while not bot.is_closed():
        assert not isinstance(channel, discord.abc.PrivateChannel)
        await channel.edit(name=f"Total Users: {len(bot.users)}")
        await asyncio.sleep(360)


async def heartbeat():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            if bot.config.heartbeat_url is not None:
                async with aiohttp.ClientSession() as session:
                    async with session.post(bot.config.heartbeat_url) as resp:
                        if resp.status != 200:
                            logging.warning(
                                f"Heartbeat failed with status {resp.status}"
                            )
        except Exception as e:
            logging.error(f"Heartbeat failed with exception {e}")
            logging.error(traceback.format_exc())

        await asyncio.sleep(30)


@bot.listen("on_ready")
async def on_ready():
    await bot.wait_until_ready()
    assert bot.user is not None, "Bot user is None, cannot proceed."

    # Get version from pyproject.toml
    try:
        with open("pyproject.toml", "r") as f:
            pyproject = toml.load(f)
            version = pyproject["tool"]["poetry"]["version"]
    except FileNotFoundError:
        version = "unknown"
    except Exception as e:
        logging.error(f"Failed to load pyproject.toml: {e}")
        version = "unknown"

    logging.info(f"Kidney Bot {version}")
    logging.info(f"Ready in {(time.perf_counter_ns() - time_start) / 1e9} seconds.")
    logging.info(f"Logged in as {bot.user} ({bot.user.id})")


@bot.listen("on_guild_join")
async def on_guild_join(guild: discord.Guild):
    if bot.user is None:
        logging.error("Bot user is None, cannot send welcome message.")
        return

    doc = await bot.database.serverbans.find_one({"id": guild.id})
    if doc is not None:
        embed = discord.Embed(
            title=f"{guild} is banned.",
            description=f"Your server *{guild}* is banned from using **{getattr(bot, 'user', 'Kidney Bot')}**.",
            color=discord.Color.red(),
        )
        owner = bot.get_user(bot.config.get_primary_owner_id())
        owner_mention = owner.mention if owner else f"<@{bot.config.get_primary_owner_id()}>"
        embed.add_field(
            name=f"You can appeal by contacting __**{owner_mention}**__.",
            value="\u2800",
        )
        
        # Handle both schema and dict access patterns
        if isinstance(doc, dict):
            reason = doc.get('reason', 'No reason provided')
        else:
            reason = getattr(doc, 'reason', 'No reason provided')
        embed.add_field(name="Reason", value=f"```{reason}```")
        
        if bot.user is not None:
            embed.set_footer(text=bot.user, icon_url=bot.user.avatar.url if bot.user.avatar else None)
        if guild.owner is not None:
            await guild.owner.send(embed=embed)

        await guild.leave()

    setup_channel = None

    setup_channel = guild.system_channel

    if setup_channel is None:
        for channel in guild.text_channels:
            if re.search(
                r"welcome|general|chat|main|lobby|bot", channel.name, re.IGNORECASE
            ):
                setup_channel = channel
                break

    if setup_channel is None:
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                setup_channel = channel
                break

    if setup_channel is None:
        if guild.owner is not None:
            setup_channel = guild.owner.dm_channel

    embed = discord.Embed(
        title="Thanks for adding me!",
        description=f"Thanks for adding me to **{guild}**!\n\nTo get started, run `/setup` in a channel where I can send messages.",
        color=discord.Color.blurple(),
    )

    bot_inviter: discord.User | discord.Member | None = None

    for integration in await guild.integrations():
        if isinstance(integration, discord.BotIntegration):
            if integration.application.id == bot.user.id:
                bot_inviter = integration.user
                break

    # Fallback that should realistically never happen
    if bot_inviter is None:
        bot_inviter = guild.owner

    # This will (hopefully) never happen
    if bot_inviter is None:
        if setup_channel is not None:
            await setup_channel.send(embed=embed)

        return

    if setup_channel is not None:
        await setup_channel.send(bot_inviter.mention, embed=embed)
    else:
        await bot_inviter.send(embed=embed)


# secret thelorbster43e mode
@bot.listen("on_message")
async def on_message(message: discord.Message):
    if message.content.lower() == "cheese":
        await message.add_reaction("🧀")


@bot.command()
@is_bot_owner()
async def testLog(ctx, actiontype, action, reason, user: discord.User):
    """Internal command for testing the log function."""
    await bot.log(ctx.guild, actiontype, action, reason, user)


@bot.command()
@is_bot_owner()
async def load(ctx, extension: str):
    """Load a cog."""
    try:
        if extension.startswith("-"):
            extension = extension[1:]
        cwd = os.path.join(os.getcwd(), "kidney-bot")
        os.rename(
            os.path.join(cwd, "cogs", f"-{extension}.py"),
            os.path.join(cwd, "cogs", f"{extension}.py"),
        )
        await bot.load_extension(f"cogs.{extension}")
        await ctx.reply(
            bot.get_lang_string("main.loaded_cog").replace("%cog%", extension)
        )
        logging.info(f"{extension.capitalize()} cog loaded.")
    except Exception as e:
        await ctx.reply(
            bot.get_lang_string("main.couldnt_load_cog")
            .replace("%cog%", extension)
            .replace("%error%", str(e))
        )


@bot.command()
@is_bot_owner()
async def unload(ctx, extension: str):
    """Unload a cog."""
    try:
        await bot.unload_extension(f"cogs.{extension}")
        cwd = os.path.join(os.getcwd(), "kidney-bot")
        os.rename(
            os.path.join(cwd, "cogs", f"{extension}.py"),
            os.path.join(cwd, "cogs", f"-{extension}.py"),
        )
        await ctx.reply(
            bot.get_lang_string("main.unloaded_cog").replace("%cog%", extension)
        )
        logging.info(f"{extension.capitalize()} cog unloaded.")
    except Exception as e:
        await ctx.reply(
            bot.get_lang_string("main.couldnt_unload_cog")
            .replace("%cog%", extension)
            .replace("%error%", str(e))
        )


@bot.command()
@is_bot_owner()
async def reload(ctx, extension: str):
    """Reload a cog."""
    try:
        await bot.unload_extension(f"cogs.{extension}")
    except Exception as e:
        await ctx.reply(
            bot.get_lang_string("main.couldnt_unload_cog")
            .replace("%cog%", extension)
            .replace("%error%", str(e))
        )
        return

    try:
        await bot.load_extension(f"cogs.{extension}")
    except Exception as e:
        await ctx.reply(
            bot.get_lang_string("main.couldnt_load_cog")
            .replace("%cog%", extension)
            .replace("%error%", str(e))
        )
        return

    await ctx.reply(
        bot.get_lang_string("main.reloaded_cog").replace("%cog%", extension)
    )
    logging.info(f"Reloaded cog {extension}")


@bot.command()
@is_bot_owner()
async def say(ctx, *, text: str):
    """Make the bot say something."""
    try:
        await ctx.message.delete()
    except:
        pass
    await ctx.channel.send(text)


@bot.command()
@is_bot_owner()
async def reply(ctx: commands.Context, message: str, *, text: str):
    """Make the bot reply to a message."""
    try:
        await ctx.message.delete()
    except:
        pass
    channel = ctx.channel
    await (await channel.fetch_message(int(message))).reply(text)


@bot.command()
@is_bot_owner()
async def react(ctx: commands.Context, message: str, reaction: str):
    """Make the bot react to a message."""
    try:
        await ctx.message.delete()
    except:
        pass
    channel = ctx.channel
    await (await channel.fetch_message(int(message))).add_reaction(reaction)


@bot.command()
@is_bot_owner()
async def raiseexception(ctx):
    """Internal command for testing error handling."""
    raise Exception("artificial exception raised")


@bot.command()
@is_bot_owner()
async def serverban(ctx: commands.Context, guild: discord.Guild, *, text: str):
    """Ban a server from using the bot."""
    n = await bot.database.serverbans.count_documents({"id": str(guild.id)})
    if n > 0:
        await ctx.channel.send("Server already banned!")
        return
    doc = {"id": guild.id, "name": guild, "owner": guild.owner, "reason": str(text)}
    await bot.database.serverbans.insert_one(doc)

    embed = discord.Embed(
        title=f"{guild} has been banned.",
        description=f"Your server *{guild}* has been banned from using **{getattr(bot, 'user', 'Kidney Bot')}**.",
        color=discord.Color.red(),
    )
    embed.add_field(
        name=f"You can appeal by contacting __**{ctx.message.author}**__.",
        value="\u2800",
    )
    embed.add_field(name="Reason", value=f"```{text}```")
    if bot.user is not None:
        if bot.user.avatar is not None:
            embed.set_footer(text=bot.user, icon_url=bot.user.avatar.url)
    if guild.owner is not None:
        await guild.owner.send(embed=embed)
    await ctx.reply(
        f"Server *{guild}* has been permanently blacklisted from using **{getattr(bot, 'user', 'Kidney Bot')}**."
    )
    await guild.leave()


@bot.command()
@is_bot_owner()
async def serverunban(ctx, guild: str):
    """Unban a server from using the bot."""
    n = await bot.database.serverbans.count_documents({"id": guild})
    if n == 0:
        await ctx.reply("Server not banned!")
        return
    await bot.database.serverbans.delete_one({"id": guild})
    await ctx.reply(
        f"Server *{guild}* has been unbanned from using **{getattr(bot, 'user', 'Kidney Bot')}**."
    )


@bot.command()
@is_bot_owner()
async def createinvite(ctx, guild: discord.Guild):
    """Create an invite to a server."""
    invite = None
    for channel in guild.text_channels:
        try:
            invite = await channel.create_invite(
                max_uses=1, reason=bot.get_lang_string("main.createinvite.reason")
            )
            break
        except:
            pass

    if invite is None:
        return await ctx.reply(
            bot.get_lang_string("main.createinvite.couldnt_create_invite")
        )

    await ctx.reply(invite)


@bot.command()
@is_bot_owner()
async def reloadconfig(ctx):
    """Reload the config file."""
    try:
        bot.config.reload()
    except Exception as e:
        await ctx.reply(f"{bot.get_lang_string("main.couldnt_reload_config")}\n`{e}`")
        return

    await ctx.reply(bot.get_lang_string("main.reloaded_config"))


@bot.command()
@is_bot_owner()
async def clearcache(ctx):
    """Clear the bot's cache."""
    for collection in bot.database.collections:
        await collection.cache.clear()

    await ctx.reply("Cache cleared.")


@bot.command()
@is_bot_owner()
async def guild_debug_info(ctx: commands.Context, guild: discord.Guild | None = None):
    message = await ctx.send("Generating debug report...")
    if guild is None:
        guild = ctx.guild

    assert guild is not None

    embed = discord.Embed(
        title=f"Debug report for {guild} ({guild.id})", color=discord.Color.blurple()
    )
    embed.add_field(
        name=guild.name,
        value=f"""**Owner:** {getattr(guild.owner, "mention", None)} ({guild.owner_id})
                    **Created:** <t:{int(guild.created_at.timestamp())}>
                    **Members:** {guild.member_count}
                    **Non-bot members:** {len([m for m in guild.members if not m.bot])}
                    **Bots:** {len([m for m in guild.members if m.bot])}""",
    )

    possible_issues = []

    if not guild.me.guild_permissions.administrator:
        possible_issues.append("Bot does not have administrator permissions.")

    # Check if bot's role is above normal members
    top_role = guild.me.top_role

    def _role_is_moderator(role: discord.Role) -> bool:
        return (
            role.permissions.administrator
            or role.permissions.manage_guild
            or role.permissions.manage_channels
            or role.permissions.manage_roles
            or role.permissions.manage_messages
            or role.permissions.ban_members
            or role.permissions.kick_members
            or role.permissions.manage_nicknames
            or role.permissions.manage_webhooks
        )

    for role in guild.roles:
        if not _role_is_moderator(role):
            if role.position > top_role.position:
                possible_issues.append(
                    f"Bot's role ({top_role.mention}) is below a normal member role ({role.mention})."
                )

    highest_member_role = None
    doc = await bot.database.autorolesettings.find_one(
        Schemas.AutoRoleSettings(guild.id)
    )
    autorole_roles = []
    if doc is not None:
        # Handle both schema and dict access patterns
        if isinstance(doc, dict):
            roles_data = doc.get("roles", [])
        else:
            roles_data = getattr(doc, 'roles', [])
            
        for role in roles_data:
            if isinstance(role, dict):
                role_id = role.get('id', 0)
            else:
                role_id = getattr(role, 'id', 0)
            _role = guild.get_role(role_id)
            if _role is not None:
                autorole_roles.append(_role)

    for role in guild.roles:
        if not _role_is_moderator(role):
            if (
                highest_member_role is None
                or role.position > highest_member_role.position
            ):
                if re.search(r"member|access|fans", role.name, re.IGNORECASE):
                    highest_member_role = role

                if role in autorole_roles:
                    highest_member_role = role

    if highest_member_role is not None:
        for role in guild.roles:
            if _role_is_moderator(role):
                if role.position < highest_member_role.position:
                    possible_issues.append(
                        f"Moderation role ({role.mention}) is below a member role ({highest_member_role.mention})."
                    )

    # TODO: check database for issues

    if len(possible_issues) == 0:
        embed.add_field(name="No issues found!", value="")
    else:
        embed.add_field(name="Possible issues:", value="\n".join(possible_issues))

    embed.set_footer(
        text=f"Debug report for {guild.name}",
        icon_url=None if guild.icon is None else guild.icon.url,
    )

    await message.edit(content="", embed=embed)


status_task: asyncio.Task | None = None
user_count_task: asyncio.Task | None = None
heartbeat_task: asyncio.Task | None = None


async def main():
    global status_task, user_count_task, heartbeat_task, cache_cleanup_task

    async with bot:
        for filename in os.listdir(os.path.join(os.path.dirname(__file__), "cogs")):
            if filename.endswith(".py"):
                if not filename.startswith("-"):
                    await bot.load_extension(f"cogs.{filename[:-3]}")

        await bot.database.connect()

        # Wait for database to connect
        while not bot.database.connected:
            await asyncio.sleep(0.1)

        status_task = asyncio.create_task(status())

        if bot.config.user_count_channel_id is not None:
            user_count_task = asyncio.create_task(user_count())
        else:
            logging.warning("No user count channel set, not counting users.")

        if bot.config.heartbeat_url is not None:
            heartbeat_task = asyncio.create_task(heartbeat())
        else:
            logging.warning("No heartbeat URL set, not sending heartbeats.")

        await bot.start(bot.config.token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logging.critical(f"Fatal error: {e}")
        logging.critical(traceback.format_exc())

    logging.info("Shutting down...")

    if status_task is not None:
        status_task.cancel()
    if user_count_task is not None:
        user_count_task.cancel()
    if heartbeat_task is not None:
        heartbeat_task.cancel()

    if bot.database.connected:
        bot.database.client.close()  # type: ignore

    asyncio.run(bot.close())

    logging.info("Shutdown complete.")
