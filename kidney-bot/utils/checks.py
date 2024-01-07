from discord.ext import commands

"""
Check if the user is the owner of the bot.
"""

def is_bot_owner():
    async def predicate(ctx: commands.Context):
        if ctx.bot.config.owner_ids is None:
            return ctx.author.id == ctx.bot.config.owner_id
        else:
            return ctx.author.id in ctx.bot.config.owner_ids
    return commands.check(predicate)

def is_guild_owner():
    async def predicate(ctx: commands.Context):
        if ctx.guild is None:
            return False
        return ctx.author.id == ctx.guild.owner.id
    return commands.check(predicate)