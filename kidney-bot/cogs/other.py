# This cog creates all uncategorized commands
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import discord
from discord.ext import commands
from discord import app_commands
import psutil
import logging
from humanfriendly import format_timespan

from utils.kidney_bot import KidneyBot
from utils.database import Schemas


class Other(commands.Cog):

    def __init__(self, bot):
        self.bot: KidneyBot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info('Other cog loaded.')

    @app_commands.command(name='invite', description='Invite the bot to your own server')
    async def invite(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Invite the bot here! https://discord.com/api/oauth2/authorize?client_id=870379086487363605&permissions=8&scope=bot")

    @app_commands.command(name='devstats', description='View the bot\'s usage of resources. Really only useful for the dev.')
    async def devstats(self, interaction: discord.Interaction):
        await interaction.response.send_message(f'ping: **{round(self.bot.latency * 1000)} ms\r**cpu:** {psutil.cpu_percent()}%\r**ram:** {psutil.virtual_memory().percent}%\r**disk:** {psutil.disk_usage("/").percent}%**', ephemeral=True)

    @app_commands.command(name='idk', description='Alec said IDK when I asked him what to make so I said kk and here it is')
    async def idk(self, interaction: discord.Interaction):
        emb = discord.Embed(color=0x313338)
        emb.set_image(url="https://www.prosurestring.xyz/alecidk.png")
        await interaction.response.send_message(embed=emb, ephemeral=True)

    @app_commands.command(name='ping', description='Get the current ping of the bot.')
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"PONG! Latency: {round(self.bot.latency * 1000)} milliseconds")

    @app_commands.command(name='info', description='View info about the bot.')
    async def info(self, interaction: discord.Interaction):
        embed = discord.Embed(title='Info', color=discord.Color.blue())
        embed.add_field(name='kidney bot is a simple all purpose discord bot',
                        value='[Support Server](https://discord.com/invite/TsuZCbz5KD) | [Invite Me!](https://discord.com/oauth2/authorize?client_id=870379086487363605&permissions=8&scope=bot) | [Website](https://kidneybot.tk) | [GitHub](https://github.com/alec-jensen/kidney-bot)',
                        inline=False)
        embed.set_footer(text=interaction.user.name, icon_url=interaction.user.avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='guild_settings_overview', description='See all settings for the current guild')
    @app_commands.default_permissions(administrator=True)
    async def guild_settings_overview(self, interaction: discord.Interaction):
        embed = discord.Embed(title='Guild Settings Overview', color=discord.Color.blue())
        doc: Schemas.ActiveGuardSettings = await self.bot.database.activeguardsettings.find_one(Schemas.ActiveGuardSettings(guild_id=interaction.guild.id), Schemas.ActiveGuardSettings)
        if doc is not None:
            embed.add_field(name='Active Guard', value=f'Block known spammers: {doc.block_known_spammers}')
        
        doc: Schemas.AiDetection = await self.bot.database.ai_detection.find_one(Schemas.AiDetection(guild=interaction.guild.id), Schemas.AiDetection)
        if doc is not None:
            embed.add_field(name='AI Detection', value=f'Enabled: {doc.enabled}\nToxicity Threshold: {doc.TOXICITY}\
            \nSevere Toxicity Threshold: {doc.SEVERE_TOXICITY}\nInsult Threshold: {doc.INSULT}\nProfanity Threshold: {doc.PROFANITY}\
            \nIdentity Attack Threshold: {doc.IDENTITY_ATTACK}\nThreat Threshold: {doc.THREAT}\nFlirtation Threshold: {doc.FLIRTATION}\
            \nObscene Threshold: {doc.OBSCENE}\nSpam Threshold: {doc.SPAM}')

        doc: Schemas.AutoModSettings = await self.bot.database.automodsettings.find_one(Schemas.AutoModSettings(guild=interaction.guild.id), Schemas.AutoModSettings)
        if doc is not None:
            whitelist = []
            for user_or_channel in doc.whitelist:
                if interaction.guild.get_member(user_or_channel) is not None:
                    whitelist.append(interaction.guild.get_member(user_or_channel).mention)
                elif interaction.guild.get_channel(user_or_channel) is not None:
                    whitelist.append(interaction.guild.get_channel(user_or_channel).mention)
                else:
                    whitelist.append(user_or_channel)

            permissions_timeout_whitelist = []
            for user in doc.permissions_timeout_whitelist:
                if interaction.guild.get_member(user) is not None:
                    permissions_timeout_whitelist.append(interaction.guild.get_member(user).mention)
                else:
                    permissions_timeout_whitelist.append(user)

            permissions_timeout = None
            if doc.permissions_timeout is not None:
                permissions_timeout = format_timespan(doc.permissions_timeout)

            embed.add_field(name='Auto Mod', value=f'Log Channel: {interaction.guild.get_channel(doc.log_channel).mention}\
                            \nWhitelist: {", ".join(whitelist)}\nPermissions Timeout: {permissions_timeout}\
                            \nPermissions Timeout Whitelist: {", ".join(permissions_timeout_whitelist)}')

        doc: Schemas.AutoRoleSettings = await self.bot.database.autorole_settings.find_one(Schemas.AutoRoleSettings(guild=interaction.guild.id), Schemas.AutoRoleSettings)
        if doc is not None:
            roles = []
            role: dict
            for role in doc.roles:
                _role = interaction.guild.get_role(role.get('id'))
                if _role is None:
                    continue

                _str = _role.mention
                try:
                    if int(role.get('delay')) > 0:
                        _str += f' (Delay: {role.get("delay")})'
                except ValueError:
                    pass
                
                roles.append(_str)

            embed.add_field(name='Auto Role', value=f'Roles: {", ".join(roles)}\nBots get roles: {doc.bots_get_roles}')

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Other(bot))
