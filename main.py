# Main file, initializes the bot.
# Copyright (C) 2022  Alec Jensen
# Full license at LICENSE.md

import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
import os
import traceback
import logging
import PermissionsChecks
import json

logging.basicConfig(level=logging.WARNING)

with open('config.json', 'r') as f:
    config = json.load(f)


async def get_prefix(client, message):
    doc = await client.database.prefixes.find_one({"id": str(message.guild.id)})
    if doc is None:
        doc = {"prefix": "."}

    return commands.when_mentioned_or(doc["prefix"])(client, message)


# bot = commands.Bot(command_prefix=(get_prefix), owner_id=766373301169160242, intents=discord.Intents.all())

class MyBot(commands.Bot):

    def __init__(self, command_prefix, owner_id, intents):
        super().__init__(
            command_prefix=command_prefix,
            owner_id=owner_id,
            intents=intents
        )
        import motor.motor_asyncio
        client = motor.motor_asyncio.AsyncIOMotorClient(config['dbstring'])
        self.database = client.data
        self.config = config

    async def setup_hook(self):
        self.tree.copy_global_to(guild=discord.Object(id=785902346894311484))
        await self.tree.sync(guild=discord.Object(id=785902346894311484))
        self.tree.copy_global_to(guild=discord.Object(id=916332743481237524))
        await self.tree.sync(guild=discord.Object(id=916332743481237524))

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


bot = MyBot(command_prefix=(get_prefix),
            owner_id=766373301169160242,
            intents=discord.Intents.all()
            )

statuses = ["with the fate of the world", "minecraft", ".help", ".prefix"]


async def status():
    await bot.wait_until_ready()
    while not bot.is_closed():
        currentstatus = random.choice(statuses)
        await bot.change_presence(activity=discord.Game(name=currentstatus))
        await asyncio.sleep(10)


@bot.listen('on_ready')
async def on_ready():
    print(f'We have logged in as {bot.user}')
    print(bot.config)


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
    await bot.database.bans.remove_many({"serverID": str(guild.ID)})
    await bot.database.prefixes.remove_many({"id": str(guild.ID)})


@bot.listen('on_message')
async def on_message(message):
    if message.content.lower() == '.prefix':
        prefix = await get_prefix(bot, message)
        await message.reply(f'My prefix in this guild is: `{prefix}`')


@app_commands.command(name="load")
@PermissionsChecks.is_owner()
async def load(interaction: discord.Interaction, extension: str):
    try:
        await bot.load_extension(f'cogs.{extension}')
        await interaction.response.send_message(f'Loaded cog {extension}')
    except Exception as e:
        await interaction.response.send_message(f'Could not load cog {extension}\n`{e}`')


@app_commands.command(name="unload")
@PermissionsChecks.is_owner()
async def unload(interaction: discord.Interaction, extension: str):
    try:
        await bot.unload_extension(f'cogs.{extension}')
        await interaction.response.send_message(f'Unlodaded cog {extension}')
    except Exception as e:
        await interaction.response.send_message(f'Could not unload cog {extension}\n`{e}`')


@app_commands.command(name="reload")
@PermissionsChecks.is_owner()
async def reload(interaction: discord.Interaction, extension: str):
    try:
        await bot.unload_extension(f'cogs.{extension}')
    except Exception as e:
        await interaction.response.send_message(f'Could not unload cog {extension}\n`{e}`')
    try:
        await bot.load_extension(f'cogs.{extension}')
        await interaction.response.send_message(f'Reloaded cog {extension}')
    except Exception as e:
        await interaction.response.send_message(f'Could not load cog {extension}\n`{e}`')


@app_commands.command(name="say")
@PermissionsChecks.is_owner()
async def say(interaction: discord.Interaction, *, text: str):
    await interaction.channel.send(text)


@app_commands.command(name="reply")
@PermissionsChecks.is_owner()
async def reply(interaction: discord.Interaction, message: int, *, text: str):
    await interaction.channel.fetch_message(message).reply(text)


@app_commands.command(name='react')
@PermissionsChecks.is_owner()
async def react(interaction: discord.Interaction, message: int, reaction: str):
    await interaction.channel.fetch_message(message).add_reaction(reaction)


@bot.listen('on_command_error')
async def on_command_error(ctx, error):
    if isinstance(error, commands.BadArgument) or isinstance(error, commands.MissingRequiredArgument):
        await ctx.channel.send(error)
    elif isinstance(error, commands.MissingPermissions):
        await ctx.channel.send(f"You don't have permission to use that command!")
    elif isinstance(error, commands.CommandNotFound):
        await ctx.message.add_reaction(r'<:no_command:955591041032007740>')
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.channel.send(f'Slow down! Try again in **{error.retry_after:.2f} seconds**')
    elif isinstance(error, commands.NotOwner):
        await ctx.message.add_reaction(r'<:no_command:955591041032007740>')
    elif isinstance(error, asyncio.exceptions.TimeoutError):
        await ctx.reply('Time is up!')
    else:
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        formattedTB = '```'
        for i in tb:
            if i == tb[-1]:
                formattedTB = f'{formattedTB}{i}```'
            else:
                formattedTB = f'{formattedTB}{i}'
        embed = discord.Embed(title='Oops! I had a problem.', color=discord.Color.red())
        embed.add_field(name='Please send this error to the developer along with the command you ran.',
                        value=formattedTB)
        try:
            await ctx.send(embed=embed)
        except:
            try:
                await ctx.send(f'Looks like I had a MASSIVE error! Please send this to the dev!\n{formattedTB}')
            except:
                print(formattedTB)


@app_commands.command()
@PermissionsChecks.is_owner()
async def announce(interaction: discord.Interaction, *, message: str):
    await interaction.response.send_message(f'Sent global message\n```{message}```', ephemeral=True)
    ids = []
    for guild in bot.guilds:
        if int(guild.owner_id) not in ids:
            await guild.owner.send(
                f'Message from the dev!\n```{message}```(you are receiving this, because you own a server with this bot)')
            ids.append(int(guild.owner_id))


@app_commands.command()
@PermissionsChecks.is_owner()
async def raiseexception(interaction: discord.Interaction):
    raise Exception('artificial exception raised')


@app_commands.command()
@PermissionsChecks.is_owner()
async def serverban(interaction: discord.Interaction, guild: int, *, text: str):
    guild = bot.get_guild(guild)
    n = await bot.database.serverbans.count_documents({"id": str(guild.id)})
    if n > 0:
        await interaction.response.send_message("Server already banned!", ephemeral=True)
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
    embed.add_field(name=f"You can appeal by contacting __**{interaction.user}**__.", value="\u2800")
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
    await interaction.response.send_message(
        f"Server *{guild}* has been permanently blacklisted from using **{bot.user.name}**")
    bot.database.serverbans.insert_one(doc)
    await guild.leave()


@app_commands.command()
@PermissionsChecks.is_owner()
async def serverunban(interaction: discord.Interaction, guild: str):
    n = await bot.database.serverbans.count_documents({"id": str(guild)})
    if n == 0:
        await interaction.response.send_message("Server not banned!")
        return
    await bot.database.serverbans.delete_one({"id": str(guild)})
    await interaction.response.send_message(f"Server *{guild}* has been unbanned from using **{bot.user.name}**")


@app_commands.command()
@PermissionsChecks.is_owner()
async def createinvite(interaction: discord.Interaction, guild: int):
    guild = bot.get_guild(guild)
    inv = 'error'
    for i in guild.text_channels:
        try:
            inv = await i.create_invite(max_uses=1, reason='bot developer requested server invite.')
            break
        except:
            pass
    await interaction.response.send_message(inv)


async def main():
    async with bot:
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                await bot.load_extension(f'cogs.{filename[:-3]}')

        await bot.load_extension('jishaku')

        asyncio.create_task(status())

        await bot.start(config['token'])


asyncio.run(main())
