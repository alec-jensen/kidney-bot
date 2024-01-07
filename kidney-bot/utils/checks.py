from discord.ext import commands

"""
Check if the user is the owner of the bot.
This is different from the is_owner() check in
discord.py because it works after config reloads.
"""

def is_owner() -> commands.check:
    async def predicate(ctx: commands.Context):
        if ctx.bot.config.owner_ids is None:
            return ctx.author.id == ctx.bot.config.owner_id
        else:
            return ctx.author.id in ctx.bot.config.owner_ids
    return commands.check(predicate)