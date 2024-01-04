from discord.ext import commands

def is_guild_owner() -> commands.check:
    async def predicate(ctx: commands.Context):
        return ctx.author.id == ctx.guild.owner_id
    return commands.check(predicate)