# This file handles command exceptions
# Copyright (C) 2022  Alec Jensen
# Full license at LICENSE.md

import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import traceback
import logging


class ExceptionHandler(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        bot.tree.on_error = self.on_app_command_error

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info('Exception-handler cog loaded.')

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error) -> None:
        if isinstance(error, commands.BadArgument) or isinstance(error, commands.MissingRequiredArgument):
            await ctx.channel.send(str(error))
        elif isinstance(error, commands.MissingPermissions):
            await ctx.channel.send(f"You don't have permission to use that command!")
        elif isinstance(error, commands.CommandNotFound):
            pass
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
                    logging.error(formattedTB)

            logging.error(f'Prefix command: {ctx.command.name}; Arguments: {ctx.kwargs}; Error: {formattedTB.replace("`", "")}')

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(f'Slow down! Try again in **{error.retry_after:.2f} seconds**', ephemeral=True)
        elif isinstance(error, app_commands.MissingPermissions):
            pass
        elif isinstance(error, asyncio.exceptions.TimeoutError):
            await interaction.channel.send('Time is up!')
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
                await interaction.response.send_message(embed=embed, ephemeral=True)
            except:
                try:
                    await interaction.response.send_message(f'Looks like I had a MASSIVE error! Please send this to the dev!\n{formattedTB}', ephemeral=True)
                except:
                    logging.error(formattedTB)
            
            logging.error(f'Application command: {interaction.command.name}; Arguments: {[param for param in interaction.namespace]}; Error: {formattedTB.replace("`", "")}')


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ExceptionHandler(bot))
