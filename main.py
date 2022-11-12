import discord
from discord.ext import commands
import random
import asyncio
import os
import traceback
import logging

logging.basicConfig(level=logging.WARNING)

dataDB = None


def initdb():
    global dataDB
    import motor.motor_asyncio
    with open('dbstring.txt') as f:
        string = f.readlines()
    client = motor.motor_asyncio.AsyncIOMotorClient(string)
    dataDB = client.data


async def get_prefix(client, message):
    doc = await dataDB.prefixes.find_one({"id": str(message.guild.id)})
    if doc is None:
        doc = {"prefix": "."}

    return commands.when_mentioned_or(doc["prefix"])(client, message)


class CustomHelpCommand(commands.HelpCommand):

    def __init__(self):
        super().__init__()

    async def send_bot_help(self, mapping):
        embed = discord.Embed(title='All Commands', color=discord.Color.blue())
        cmdlist = ''
        for cog in mapping:
            try:
                if cog.qualified_name != "Jishaku":
                    for cmd in [command.name for command in mapping[cog]]:
                        if cmdlist:
                            cmdlist = f"{cmdlist}, {cmd}"
                        else:
                            cmdlist = cmd
                    embed.add_field(name=cog.qualified_name, value=cmdlist)
                    cmdlist = ''
            except:
                pass
        embed.add_field(name='Type "help <command>" or "help <category>" for more information.', value='[Support Server](https://discord.com/invite/TsuZCbz5KD) | [Invite Me!](https://discord.com/oauth2/authorize?client_id=870379086487363605&permissions=8&scope=bot) | [Website](https://kidneybot.tk)', inline=False)
        embed.set_footer(text=self.context.author,icon_url=self.context.author.avatar)
        await self.context.send(embed=embed)

    async def send_cog_help(self, cog):
        embed = discord.Embed(title=f'{cog.qualified_name} Commands', color=discord.Color.blue())
        cmdlist = ''
        for cmd in [command for command in cog.get_commands()]:
            if cmdlist:
                cmdlist = f"{cmdlist}\n{cmd.name} - {cmd.brief}"
            else:
                cmdlist = f"{cmd.name} - {cmd.brief}"
        embed.add_field(name=cog.qualified_name, value=cmdlist)
        embed.set_footer(text=self.context.author,icon_url=self.context.author.avatar)
        await self.context.send(embed=embed)

    async def send_group_help(self, group):
        await self.get_destination().send(f'{group.name}: {command.name for index, command in enumerate(group.commands)}')

    async def send_command_help(self, command):
        embed = discord.Embed(title=f'{get_prefix(None, self.context)}{command.name}', color=discord.Color.blue())
        params = ''
        for param in list(command.clean_params.keys()):
            if not command.params[param].default:
                if not params:
                    params = f'({param})'
                else:
                    params = f'{params} ({param})'
            else:
                if not params:
                    params = f'<{param}>'
                else:
                    params = f'{params} <{param}>'
        aliases = ''
        for alias in command.aliases:
            if not aliases:
                aliases = f'`{alias}`'
            else:
                aliases = f'{aliases}, `{alias}`'
        paramdef = '<required>, (optional)\n\n' if params != '' else '\u2800'
        aliasdef = f'\nAliases: {aliases}' if aliases != '' else '\u2800'
        embed.add_field(name=f'{get_prefix(None, self.context)}{command.name} {params}', value=f'{paramdef}{command.help}{aliasdef}')
        embed.set_footer(text=self.context.author,icon_url=self.context.author.avatar)
        await self.context.send(embed=embed)


bot = commands.Bot(command_prefix=(get_prefix), owner_id=766373301169160242, intents=discord.Intents.all(), help_command=CustomHelpCommand())


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
        

@bot.listen('on_guild_join')
async def on_guild_join(guild):
    n = await dataDB.serverbans.count_documents({"id": str(guild.id)})
    if n > 0:
        doc = await dataDB.serverbans.find_one({"id": str(guild.id)})
        embed = discord.Embed(title=f"{guild} is banned.",
                              description=f"Your server *{guild}* is banned from using **{bot.user.name}**.",
                              color=discord.Color.red())
        embed.add_field(name=f"You can appeal by contacting __**{bot.get_user(766373301169160242)}**__.", value="\u2800")
        embed.add_field(name="Reason", value=f"```{doc['reason']}```")
        embed.set_footer(text=bot.user, icon_url=bot.user.avatar)
        await guild.owner.send(embed=embed)
        await guild.leave()


@bot.listen('on_guild_remove')
async def on_guild_remove(guild):
    await dataDB.bans.remove_many({"serverID": str(guild.ID)})
    await dataDB.prefixes.remove_many({"id": str(guild.ID)})


@bot.listen('on_message')
async def on_message(message):
    if message.content.lower() == '.prefix':
        prefix = await get_prefix(bot, message)
        await message.reply(f'My prefix in this guild is: `{prefix}`')


@bot.command()
@commands.is_owner()
async def load(ctx, extension):
    try:
        await bot.load_extension(f'cogs.{extension}')
        await ctx.message.reply(f'Loaded cog {extension}')
    except Exception as e:
        await ctx.message.reply(f'Could not load cog {extension}\n`{e}`')


@bot.command()
@commands.is_owner()
async def unload(ctx, extension):
    try:
        await bot.unload_extension(f'cogs.{extension}')
        await ctx.message.reply(f'Unlodaded cog {extension}')
    except Exception as e:
        await ctx.message.reply(f'Could not unload cog {extension}\n`{e}`')


@bot.command()
@commands.is_owner()
async def reload(ctx, extension):
    try:
        await bot.unload_extension(f'cogs.{extension}')
        await ctx.message.reply(f'Unlodaded cog {extension}')
    except Exception as e:
        await ctx.message.reply(f'Could not unload cog {extension}\n`{e}`')
    try:
        await bot.load_extension(f'cogs.{extension}')
        await ctx.message.reply(f'Loaded cog {extension}')
    except Exception as e:
        await ctx.message.reply(f'Could not load cog {extension}\n`{e}`')


@bot.command()
@commands.is_owner()
async def say(ctx, *, text):
    if ctx.author.id == 766373301169160242:
        await ctx.message.delete()
        await ctx.channel.send(text)


@bot.listen('on_command_error')
async def on_command_error(ctx, error):
    if isinstance(error, commands.BadArgument) or isinstance(error, commands.MissingRequiredArgument):
        await ctx.channel.send(error)
    elif isinstance(error, commands.MissingPermissions):
        await ctx.channel.send( f"You don't have permission to use that command!")
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
        embed.add_field(name='Please send this error to the developer along with the command you ran.', value=formattedTB)
        try:
            await ctx.send(embed=embed)
        except:
            await ctx.send(f'Looks like I had a MASSIVE error! Please send this to the dev!\n{formattedTB}')

@bot.command()
@commands.is_owner()
async def announce(ctx, *, message):
    await ctx.send(f'Sent global message\n```{message}```')
    ids = []
    for guild in bot.guilds:
        if int(guild.owner_id) not in ids:
            await guild.owner.send(f'Message from the dev!\n```{message}```(you are receiving this, because you own a server with this bot)')
            ids.append(int(guild.owner_id))



@bot.command()
@commands.is_owner()
async def raiseexception(ctx):
    raise Exception('artificial exception raised')

@bot.command()
@commands.is_owner()
async def serverban(ctx, guild: discord.Guild, *, text):
    if ctx.message.author.id == 766373301169160242:
        n = await dataDB.serverbans.count_documents({"id": str(guild.id)})
        if n > 0:
            await ctx.reply("Server already banned!")
            return
        doc = {
            "id": str(guild.id),
            "name": str(guild),
            "owner": str(guild.owner),
            "reason": str(text)
        }
        embed = discord.Embed(title=f"{guild} has been banned.", description=f"Your server *{guild}* has been banned from using **{bot.user.name}**.", color=discord.Color.red())
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
        await ctx.message.reply(f"Server *{guild}* has been permanently blacklisted from using **{bot.user.name}**")
        dataDB.serverbans.insert_one(doc)
        await guild.leave()


@bot.command()
@commands.is_owner()
async def serverunban(ctx, guild):
    if ctx.message.author.id == 766373301169160242:
        n = await dataDB.serverbans.count_documents({"id": str(guild)})
        if n == 0:
            await ctx.reply("Server not banned!")
            return
        await dataDB.serverbans.delete_one({"id": str(guild)})
        await ctx.message.reply(f"Server *{guild}* has been unbanned from using **{bot.user.name}**")





@bot.command()
@commands.is_owner()
async def createinvite(ctx, guild: discord.Guild):
    if ctx.message.author.id == 766373301169160242:
        inv = 'error'
        for i in guild.text_channels:
            try:
                inv = await i.create_invite(max_uses=1,reason='bot developer requested server invite.')
                break
            except:
                pass
        await ctx.message.reply(inv)

async def main():
    async with bot:
        initdb()

        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                await bot.load_extension(f'cogs.{filename[:-3]}')

        await bot.load_extension('jishaku')

        asyncio.create_task(status())

        with open('token.txt') as f:
            lines = f.readlines()

        await bot.start(str(lines[0]))

asyncio.run(main())
