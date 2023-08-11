# This cog creates all automod commands
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import discord
from discord.ext import commands
from discord import  app_commands
import logging
import aiohttp
from typing import Literal
from utils.kidney_bot import KidneyBot

class Automod(commands.Cog):

    def __init__(self, bot):
        self.bot: KidneyBot = bot
        

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info('Automod cog loaded.')
        if self.bot.config.perspective_api_key is None:
            logging.warning('Perspective API key not set. AI detection will not work.')


    @commands.Cog.listener()
    async def on_message(self, message):
        try:    
            doc = await self.bot.database.ai_detection.find_one({'guild': message.guild.id})
            if doc is None or doc.get('enabled') is False:
                return
            if message.author.bot:
                return
        except AttributeError: return

        if self.bot.config.perspective_api_key is None:
            return

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
                            await self.bot.log(message.guild, 'Automod', 'AI Detection', f'{key} >= {doc.get(key)}', user=message.guild.me, target=message.author, message=message)
                            return

        
    auto_mod = app_commands.Group(name='automod', description='Manage Automod settings',
                                      default_permissions=discord.Permissions(manage_guild=True))

    @auto_mod.command(name='ai', description='Manage AI automod settings. Recommended to set to 70-80% for best results.')
    async def automod(self, interaction: discord.Interaction, enabled: bool=None, option: Literal['TOXICITY', 'SEVERE_TOXICITY', 'IDENTITY_ATTACK', 'INSULT', 'PROFANITY', 'THREAT', 'FLIRTATION', 'OBSCENE', 'SPAM']=None, value: int=None):
        if enabled is False:
            await self.bot.database.ai_detection.update_one({'guild': interaction.guild.id}, {'$set': {'enabled': False}})
            await interaction.response.send_message(f'AI Detection disabled.', ephemeral=True)
            return
        elif enabled is True:
            await self.bot.database.ai_detection.update_one({'guild': interaction.guild.id}, {'$set': {'enabled': True}})
            await interaction.response.send_message(f'AI Detection enabled.', ephemeral=True)
            return
            
        if option is not None and value is None:
            await interaction.response.send_message(f'Invalid arguments. Please provide a value.', ephemeral=True)
            return
        if option is not None and value is not None and value < 0 or value > 100:
            await interaction.response.send_message(f'Invalid value. Value must be between 0 and 100.', ephemeral=True)
            return
        if enabled is None and (option is None or value is None):
            await interaction.response.send_message(f'Invalid arguments. Please provide an option and value.', ephemeral=True)
            return
        if option is None and enabled is None and value is None:
            await interaction.response.send_message(f'Invalid arguments. Please provide an enabled state, or an option and value.', ephemeral=True)
            return

        if await self.bot.database.ai_detection.find_one({'guild': interaction.guild.id}) is not None:
            await self.bot.database.ai_detection.update_one({'guild': interaction.guild.id}, {'$set': {option: value}})
        else:
            await self.bot.database.ai_detection.insert_one({'guild': interaction.guild.id, option: value})
        
        await interaction.response.send_message(f'`{option}` set to `{value}`', ephemeral=True)
    
    @auto_mod.command(name='ai_overview', description='View AI automod settings')
    async def automod_overview(self, interaction: discord.Interaction):
        doc = await self.bot.database.ai_detection.find_one({'guild': interaction.guild.id})
        if doc is None:
            await interaction.response.send_message(f'AI Detection is disabled.', ephemeral=True)
            return
        embed = discord.Embed(title='AI Detection Overview', description='AI Detection is currently enabled. The following settings are set:', color=discord.Color.green())
        for key, value in doc.items():
            if key == '_id' or key == 'guild':
                continue
            embed.add_field(name=key, value=value, inline=True)
        await interaction.response.send_message(embeds=[embed], ephemeral=True)

    @auto_mod.command(name='log', description='Set the log channel for automod')
    async def automod_log(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if await self.bot.database.automodsettings.find_one({'guild': interaction.guild.id}) is not None:
            await self.bot.database.automodsettings.update_one({'guild': interaction.guild.id}, {'$set': {'log_channel': channel.id}})
        else:
            await self.bot.database.automodsettings.insert_one({'guild': interaction.guild.id, 'log_channel': channel.id})

        await interaction.response.send_message(f'Log channel set to {channel.mention}', ephemeral=True)


async def setup(bot):
    automod = Automod(bot)
    if bot.config.perspective_api_key is None:
        automod.auto_mod = None
    await bot.add_cog(automod)
