# This cog creates all uncategorized commands
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

from typing import Literal
import discord
from discord.ext import commands
from discord import app_commands
import psutil
import logging
from humanfriendly import format_timespan

from utils.kidney_bot import KidneyBot
from utils.database import Schemas
from utils import checks


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
        avatar_url = interaction.user.avatar
        if avatar_url is not None:
            avatar_url = avatar_url.url
        embed.set_footer(text=interaction.user.name, icon_url=avatar_url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='guild_settings_overview', description='See all settings for the current guild')
    @app_commands.default_permissions(administrator=True)
    async def guild_settings_overview(self, interaction: discord.Interaction):
        embed = discord.Embed(title='Guild Settings Overview', color=discord.Color.blue())
        doc: Schemas.ActiveGuardSettings = await self.bot.database.activeguardsettings.find_one(Schemas.ActiveGuardSettings(guild_id=interaction.guild.id), Schemas.ActiveGuardSettings)
        if doc is not None:
            embed.add_field(name='Active Guard', value=f'Block known spammers: {doc.block_known_spammers}')
        
        doc1: Schemas.AiDetection = await self.bot.database.ai_detection.find_one(Schemas.AiDetection(guild=interaction.guild.id), Schemas.AiDetection)
        if doc1 is not None:
            embed.add_field(name='AI Detection', value=f'Enabled: {doc1.enabled}\nToxicity Threshold: {doc1.TOXICITY}\
            \nSevere Toxicity Threshold: {doc1.SEVERE_TOXICITY}\nInsult Threshold: {doc1.INSULT}\nProfanity Threshold: {doc1.PROFANITY}\
            \nIdentity Attack Threshold: {doc1.IDENTITY_ATTACK}\nThreat Threshold: {doc1.THREAT}\nFlirtation Threshold: {doc1.FLIRTATION}\
            \nObscene Threshold: {doc1.OBSCENE}\nSpam Threshold: {doc1.SPAM}')

        doc2: Schemas.AutoModSettings = await self.bot.database.automodsettings.find_one(Schemas.AutoModSettings(guild=interaction.guild.id), Schemas.AutoModSettings)
        if doc2 is not None:
            whitelist = []

            if interaction.guild is None:
                return
            
            for user_or_channel in getattr(doc2, 'whitelist', []):
                if interaction.guild.get_member(user_or_channel) is not None:
                    whitelist.append(interaction.guild.get_member(user_or_channel).mention)
                elif interaction.guild.get_channel(user_or_channel) is not None:
                    whitelist.append(interaction.guild.get_channel(user_or_channel).mention)
                else:
                    whitelist.append(user_or_channel)

            permissions_timeout_whitelist = []
            for user in getattr(doc2, 'permissions_timeout_whitelist', []):
                if interaction.guild.get_member(user) is not None:
                    permissions_timeout_whitelist.append(interaction.guild.get_member(user).mention)
                else:
                    permissions_timeout_whitelist.append(user)

            permissions_timeout = None
            if doc2.permissions_timeout is not None:
                permissions_timeout = format_timespan(doc2.permissions_timeout)

            embed.add_field(name='Auto Mod', value=f'Log Channel: {None if doc2.log_channel is None else \
                                                                   getattr(interaction.guild.get_channel(doc2.log_channel), \
                                                                           "mention", None)}\
                            \nWhitelist: {", ".join(whitelist)}\nPermissions Timeout: {permissions_timeout}\
                            \nPermissions Timeout Whitelist: {", ".join(permissions_timeout_whitelist)}')

        doc3: Schemas.AutoRoleSettings = await self.bot.database.autorole_settings.find_one(Schemas.AutoRoleSettings(guild=interaction.guild.id), Schemas.AutoRoleSettings)
        if doc3 is not None:
            roles = []
            role: dict
            for role in getattr(doc3, 'roles', []):
                _role = interaction.guild.get_role(role[id])
                if _role is None:
                    continue

                _str = _role.mention
                try:
                    if int(role.get('delay', 0)) > 0:
                        _str += f' (Delay: {role.get("delay")})'
                except ValueError:
                    pass
                
                roles.append(_str)

            embed.add_field(name='Auto Role', value=f'Roles: {", ".join(roles)}\nBots get roles: {doc3.bots_get_roles}')

        await interaction.response.send_message(embed=embed, ephemeral=True)

    """
    Announce levels
    0 - No announcements
    1 - Critical announcements only
    2 - Update announcements
    3 - All announcements
    """

    announce_levels = {
        0: 'None',
        1: 'Critical',
        2: 'Update',
        3: 'All'
    }

    @app_commands.command(name='set_announce_level', description='Set the level of announcements you want to receive from the bot.')
    @app_commands.describe(level="Level of announcements you want to recieve. You will receive all announcements of this level and below.")
    async def set_announce_level(self, interaction: discord.Interaction, level: Literal["None", "Critical", "Update", "All"]):
        announce_level = {v: k for k, v in self.announce_levels.items()}[level]

        await self.bot.database.user_config.update_one(Schemas.UserConfig(user_id=interaction.user.id), {'$set': {'announce_level': announce_level}}, upsert=True)
        await interaction.response.send_message(f'Announce level set to {level}', ephemeral=True)

    @commands.command()
    @checks.is_bot_owner()
    async def announce(self, ctx, level: str, *, message: str):
        """Send a global message to all server owners."""

        level = level.title()

        if not level in self.announce_levels and not level in self.announce_levels.values():
            await ctx.reply(self.bot.get_lang_string('other.announce.invalid_level'))
            return

        if level.isdigit():
            announce_level = int(level)
        else:
            announce_level = {v: k for k, v in self.announce_levels.items()}.get(level)

        if announce_level is None:
            await ctx.reply(self.bot.get_lang_string('other.announce.invalid_level'))
            return

        await ctx.reply(f'Sending global message\n```{message}```')
        ids = []
        for guild in self.bot.guilds:
            if guild.owner is None: continue
            if int(guild.owner.id) not in ids:
                user_config = await self.bot.database.user_config.find_one(Schemas.UserConfig(user_id=guild.owner.id), Schemas.UserConfig)

                assert type(user_config) == Schemas.UserConfig or user_config is None

                if user_config is None:
                    user_config = Schemas.UserConfig(user_id=guild.owner.id, announce_level=1)

                if user_config.announce_level is None:
                    user_config.announce_level = 1

                if user_config.announce_level == 0:
                    continue

                if user_config.announce_level < announce_level:
                    continue

                successfully_sent = 0
                not_sent = 0

                try:
                    await guild.owner.send(
                        f'Message from the dev!\n```{message}```(you are receiving this, because you own a server with this bot. If you do not want to receive these messages, run `/set_announce_level <level>`)')
                    ids.append(int(guild.owner.id))
                    successfully_sent += 1
                except:
                    not_sent += 1

                await ctx.reply(f'Successfully sent to {successfully_sent} guild owners, {not_sent} not sent.')

async def setup(bot):
    await bot.add_cog(Other(bot))
