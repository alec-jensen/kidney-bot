# This cog creates all automod commands
# Copyright (C) 2022  Alec Jensen
# Full license at LICENSE.md

import discord
from discord.ext import commands
from discord import  app_commands
import logging
import aiohttp
from typing import Literal

class Automod(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    async def log(self, action, reason, message):
        doc = await self.bot.database.automodsettings.find_one({'guild': message.guild.id})
        if doc is None:
            return
        if doc.get('log_channel') is None:
            return
        
        embed = discord.Embed(title=f'Automod: {action}', description=f'**User:** {message.author.mention}\n**Reason:** {reason}\n**Message:** ```{message.content}```', color=discord.Color.red())
        embed.set_footer(text=f'User ID: {message.author.id}')
        await self.bot.get_channel(doc['log_channel']).send(embed=embed)


    @commands.Cog.listener()
    async def on_ready(self):
        logging.info('Automod cog loaded.')


    @commands.Cog.listener()
    async def on_message(self, message):
        try:    
            doc = await self.bot.database.ai_detection.find_one({'guild': message.guild.id})
            if doc is None or doc.get('enabled') is False:
                return
            if message.author.bot:
                return
        except AttributeError: return

        headers = {"Content-Type": "application/json"}
        data = '{comment: {text: "' + message.content + '"}, languages: ["en"], requestedAttributes: {TOXICITY:{}, SEVERE_TOXICITY: {}, IDENTITY_ATTACK: {}, INSULT: {}, PROFANITY: {}, THREAT: {}, FLIRTATION: {}, OBSCENE: {}, SPAM: {}} }'

        async with aiohttp.ClientSession() as session:
            async with session.post(f"https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze?key={self.bot.config.perspective_api_key}", headers=headers, data=data) as resp:
                resp_json = await resp.json()
                for key, value in resp_json['attributeScores'].items():
                    logging.debug(f"{key}: {int(float(value['summaryScore']['value'])*100)}%")
                    if doc is not None and doc.get(key) is not None:
                        if int(float(value['summaryScore']['value'])*100) >= doc.get(key):
                            await message.delete()
                            await message.author.send(f'Your message ```{message.content}``` was deleted because it was detected that `{key} >= {doc.get(key)}`')
                            await self.log('AI Detection', f'{key} >= {doc.get(key)}', message)
                            return

        
    
    auto_mod = app_commands.Group(name='automod', description='Manage Automod settings',
                                      default_permissions=discord.Permissions(manage_guild=True))

    @auto_mod.command(name='ai', description='Manage AI automod settings. Recommended to set to 70-80% for best results.')
    async def automod(self, interaction: discord.Interaction, enabled: bool=None, option: Literal['TOXICITY', 'SEVERE_TOXICITY', 'IDENTITY_ATTACK', 'INSULT', 'PROFANITY', 'THREAT', 'FLIRTATION', 'OBSCENE', 'SPAM']=None, value: int=None):
        if value < 0 or value > 100:
            await interaction.response.send_message(f'Invalid value. Value must be between 0 and 100.', ephemeral=True)
            return
        if interaction is None and (option is None or value is None):
            await interaction.response.send_message(f'Invalid arguments. Please provide an option and value.', ephemeral=True)
            return
        if interaction is None and enabled is None:
            await interaction.response.send_message(f'Invalid arguments. Please provide an enabled state.', ephemeral=True)
            return
        if option is not None and value is None:
            await interaction.response.send_message(f'Invalid arguments. Please provide a value.', ephemeral=True)
            return

        if enabled is False:
            await self.bot.database.ai_detection.update_one({'guild': interaction.guild.id}, {'$set': {'enabled': False}})
            await interaction.response.send_message(f'AI Detection disabled.', ephemeral=True)
            return
        elif enabled is True:
            await self.bot.database.ai_detection.update_one({'guild': interaction.guild.id}, {'$set': {'enabled': True}})
            await interaction.response.send_message(f'AI Detection enabled.', ephemeral=True)
            return
        
        if await self.bot.database.ai_detection.find_one({'guild': interaction.guild.id}) is not None:
            await self.bot.database.ai_detection.update_one({'guild': interaction.guild.id}, {'$set': {option: value}})
        else:
            await self.bot.database.ai_detection.insert_one({'guild': interaction.guild.id, option: value})
        
        await interaction.response.send_message(f'`{option}` set to `{value}`', ephemeral=True)

    @auto_mod.command(name='log', description='Set the log channel for automod')
    async def automod_log(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if await self.bot.database.automodsettings.find_one({'guild': interaction.guild.id}) is not None:
            await self.bot.database.automodsettings.update_one({'guild': interaction.guild.id}, {'$set': {'log_channel': channel.id}})
        else:
            await self.bot.database.automodsettings.insert_one({'guild': interaction.guild.id, 'log_channel': channel.id})

        await interaction.response.send_message(f'Log channel set to {channel.mention}', ephemeral=True)


async def setup(bot):
    await bot.add_cog(Automod(bot))
