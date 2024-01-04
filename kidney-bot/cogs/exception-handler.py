# This file handles command exceptions
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import traceback
import logging
from uuid import uuid4

from utils.kidney_bot import KidneyBot
from utils.database import Schemas

error_buffer = {}


class ExceptionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def disable_buttons(self, interaction: discord.Interaction):
        for child in self.children:
            child.disabled = True

        await interaction.followup.edit_message(interaction.message.id, view=self)

    @discord.ui.button(label='Report error', style=discord.ButtonStyle.blurple)
    async def report(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = None

        if len(interaction.message.embeds) > 0:
            user_id = interaction.message.embeds[0].footer.text.split('user_id(')[
                1].split(')')[0]
        else:
            user_id = interaction.message.content.split('user_id(')[1].split(')')[
                0]

        if user_id is None:
            return

        if interaction.user.id != int(user_id):
            await interaction.response.send_message('You cannot report someone else\'s error!')
            return

        exception_id = None

        if len(interaction.message.embeds) > 0:
            exception_id = interaction.message.embeds[0].footer.text.split('id(')[
                1].split(')')[0]
        else:
            exception_id = interaction.message.content.split('id(')[1].split(')')[
                0]

        if exception_id is None:
            await interaction.response.send_message('Error could not be reported!')
            return

        await interaction.response.send_message('Error reported!')
        logging.error(error_buffer[exception_id])

        bot: KidneyBot = interaction.client
        if bot.config.error_channel is not None:
            channel: discord.TextChannel = interaction.guild.get_channel(
                bot.config.error_channel)
            await channel.send(f"```{error_buffer[exception_id]}```")

        del error_buffer[exception_id]

        await self.disable_buttons(interaction)

    @discord.ui.button(label='Always report errors', style=discord.ButtonStyle.green)
    async def report_always(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = None

        if len(interaction.message.embeds) > 0:
            user_id = interaction.message.embeds[0].footer.text.split('user_id(')[
                1].split(')')[0]
        else:
            user_id = interaction.message.content.split('user_id(')[1].split(')')[
                0]

        if user_id is None:
            return

        if interaction.user.id != int(user_id):
            await interaction.response.send_message('You cannot report someone else\'s error!')
            return

        exception_id = None

        if len(interaction.message.embeds) > 0:
            exception_id = interaction.message.embeds[0].footer.text.split('id(')[
                1].split(')')[0]
        else:
            exception_id = interaction.message.content.split('id(')[1].split(')')[
                0]

        if exception_id is None:
            await interaction.response.send_message('Error could not be reported!')
            return

        await interaction.response.send_message('Error reported!\nFuture errors will be reported automatically.')
        logging.error(error_buffer[exception_id])

        bot: KidneyBot = interaction.client
        if bot.config.error_channel is not None:
            channel: discord.TextChannel = interaction.guild.get_channel(
                bot.config.error_channel)
            await channel.send(f"```{error_buffer[exception_id]}```")

        del error_buffer[exception_id]

        doc = await bot.database.exceptions.find_one(Schemas.ExceptionSchema(interaction.user.id))
        if doc is None:
            await bot.database.exceptions.insert_one(Schemas.ExceptionSchema(interaction.user.id, True))
        else:
            await bot.database.exceptions.update_one({'user_id': interaction.user.id}, {'$set': {'always_report_errors': True}})

        await self.disable_buttons(interaction)

    @discord.ui.button(label='Ignore error', style=discord.ButtonStyle.red)
    async def ignore(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = None

        if len(interaction.message.embeds) > 0:
            user_id = interaction.message.embeds[0].footer.text.split('user_id(')[
                1].split(')')[0]
        else:
            user_id = interaction.message.content.split('user_id(')[1].split(')')[
                0]

        if user_id is None:
            return

        if interaction.user.id != int(user_id):
            await interaction.channel.send('You cannot report someone else\'s error!')
            return

        exception_id = None

        if len(interaction.message.embeds) > 0:
            exception_id = interaction.message.embeds[0].footer.text.split('id(')[
                1].split(')')[0]
        else:
            exception_id = interaction.message.content.split('id(')[1].split(')')[
                0]

        if exception_id is None:
            await interaction.channel.send('Error could not be reported!')
            return

        await interaction.channel.send(f'Error ignored! ID: {exception_id}')
        del error_buffer[exception_id]

        await self.disable_buttons(interaction)


class ExceptionHandler(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: KidneyBot = bot
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
            exception_id = str(uuid4())
            tb = traceback.format_exception(
                type(error), error, error.__traceback__)
            formattedTB = '```'
            for i in tb:
                formattedTB += i
            formattedTB += '```'

            error_buffer[
                exception_id] = f'Prefix command: {ctx.command.name}; Arguments: {ctx.kwargs}; Error: {formattedTB.replace("`", "")}'

            doc = await self.bot.database.exceptions.find_one(Schemas.ExceptionSchema(ctx.author.id))
            if doc is not None:
                if doc['always_report_errors']:
                    logging.error(error_buffer[exception_id])
                    await self.bot.get_channel(self.bot.config.error_channel).send(f"```{error_buffer[exception_id]}```")
                    await ctx.send(f'Reported error to developer...\n{formattedTB}')
                    del error_buffer[exception_id]
                    return
                
            embed = discord.Embed(
                title='Oops! I had a problem.', color=discord.Color.red())
            embed.add_field(name='Please send this error to the developer along with the command you ran.',
                            value=formattedTB)
            embed.set_footer(
                text=f'id({exception_id}), user_id({ctx.author.id})')
            try:
                await ctx.send(embed=embed, view=ExceptionView())
            except:
                try:
                    await ctx.send(f'Looks like I had a MASSIVE error! Please send this to the dev!\n{formattedTB}\nid({exception_id}), user_id({ctx.author.id})', view=ExceptionView())
                except:
                    await ctx.send(f'An error has occured.\nid({exception_id}), user_id({ctx.author.id})', view=ExceptionView())

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(f'Slow down! Try again in **{error.retry_after:.2f} seconds**', ephemeral=True)
        elif isinstance(error, app_commands.MissingPermissions):
            pass
        elif isinstance(error, asyncio.exceptions.TimeoutError):
            await interaction.channel.send('Time is up!')
        else:
            exception_id = str(uuid4())
            tb = traceback.format_exception(
                type(error), error, error.__traceback__)
            formattedTB = '```'
            for i in tb:
                formattedTB += i
            formattedTB += '```'

            error_buffer[exception_id] = f'Application command: {interaction.command.name}; Arguments: {[param for param in interaction.namespace]}; \
                          Error: {formattedTB.replace("`", "")}'

            doc = await self.bot.database.exceptions.find_one(Schemas.ExceptionSchema(interaction.user.id))
            if doc is not None:
                if doc['always_report_errors']:
                    logging.error(error_buffer[exception_id])
                    await self.bot.get_channel(self.bot.config.error_channel).send(f"```{error_buffer[exception_id]}```")
                    interaction.response.send_message(f'Reported error to developer...\n{formattedTB}')
                    del error_buffer[exception_id]
                    return
                
            embed = discord.Embed(
                title='Oops! I had a problem.', color=discord.Color.red())
            embed.add_field(name='Please send this error to the developer along with the command you ran.',
                            value=formattedTB)
            embed.set_footer(
                text=f'id({exception_id}), user_id({interaction.user.id})')
            try:
                await interaction.response.send_message(embed=embed, ephemeral=True, view=ExceptionView())
            except:
                try:
                    await interaction.response.send_message(f'Looks like I had a MASSIVE error! Please send this to the dev!\n{formattedTB}id({exception_id}), user_id({interaction.user.id})', ephemeral=True, view=ExceptionView())
                except:
                    await interaction.response.send_message(f'An error has occured.\nid({exception_id}), user_id({interaction.user.id})', ephemeral=True, view=ExceptionView())
                
    @app_commands.command(name='always_report_errors', description='Toggle whether or not to always report errors to the developer.')
    async def always_report_errors(self, interaction: discord.Interaction, value: bool):
        doc = await self.bot.database.exceptions.find_one(Schemas.ExceptionSchema(interaction.user.id))
        if doc is None:
            await self.bot.database.exceptions.insert_one(Schemas.ExceptionSchema(interaction.user.id, value))
            await interaction.response.send_message('You will now always report errors to the developer.', ephemeral=True)
        else:
            await self.bot.database.exceptions.update_one({'user_id': interaction.user.id}, {'$set': {'always_report_errors': value}})
            if value:
                await interaction.response.send_message('You will now always report errors to the developer.', ephemeral=True)
            else:
                await interaction.response.send_message('You will no longer always report errors to the developer.', ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ExceptionHandler(bot))
