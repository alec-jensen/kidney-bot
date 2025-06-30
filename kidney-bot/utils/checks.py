from discord.ext import commands

"""
Check if the user is the owner of the bot.
"""

def is_bot_owner():
    async def predicate(ctx: commands.Context):
        return ctx.bot.config.is_owner(ctx.author.id)
    return commands.check(predicate)

def is_guild_owner():
    async def predicate(ctx: commands.Context):
        if ctx.guild is None:
            return False
        if ctx.guild.owner is None:
            return False
        return ctx.author.id == ctx.guild.owner.id
    return commands.check(predicate)