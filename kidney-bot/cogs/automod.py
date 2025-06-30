# This cog creates all automod commands
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import discord
from discord.ext import commands
from discord import app_commands
import logging
import aiohttp
from typing import Literal

from utils.kidney_bot import KidneyBot
from utils.audit_log_utils import AuditLogCheckTypes, attempt_undo_audit_log_action
from utils import checks

moderation_permissions = [
    'administrator',
    'ban_members',
    'deafen_members',
    'kick_members',
    'manage_channels',
    'manage_emojis',
    'manage_emojis_and_stickers',
    'manage_events',
    'manage_guild',
    'manage_messages',
    'manage_nicknames',
    'manage_permissions',
    'manage_roles',
    'manage_threads',
    'manage_webhooks',
    'manage_webhooks',
    'mention_everyone',
    'moderate_members',
    'move_members',
    'mute_members',
    'view_audit_log',
    'view_guild_insights'
]


class Automod(commands.Cog):

    def __init__(self, bot):
        self.bot: KidneyBot = bot

    async def ai_detect(self, content: str, guild: discord.Guild, doc: dict | object | None = None) -> dict | None:
        if self.bot.config.perspective_api_key is None:
            return None

        headers = {"Content-Type": "application/json"}
        data = '{comment: {text: "' + content + \
            '"}, languages: ["en"], requestedAttributes: {TOXICITY:{}, SEVERE_TOXICITY: {}, IDENTITY_ATTACK: {}, INSULT: {}, PROFANITY: {}, THREAT: {}, FLIRTATION: {}, OBSCENE: {}, SPAM: {}} }'

        async with aiohttp.ClientSession() as session:
            async with session.post(f"https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze?key={self.bot.config.perspective_api_key}", headers=headers, data=data) as resp:
                resp_json = await resp.json()

                if resp.status != 200:
                    logging.warning(
                        f'Perspective API returned status code {resp.status} with response {resp_json}')
                    return None

                if doc is None:
                    doc_result = await self.bot.database.ai_detection.find_one({'guild': guild.id})
                    if doc_result is None:
                        return None
                    # Use the doc_result directly
                    doc = doc_result

                detections = {}
                if resp_json.get('attributeScores') is None:
                    return None
                for key, value in resp_json['attributeScores'].items():
                    # deepcode ignore AttributeLoadOnNone: this warning is incorrect
                    # Safe access for both dict and schema
                    threshold = doc.get(key, 60) if isinstance(doc, dict) else getattr(doc, key, 60)
                    if value['summaryScore']['value'] > threshold / 100:
                        detections[key] = value

                return detections

    async def check_whitelist(self, member_or_channel: discord.Member | discord.TextChannel):
        doc = await self.bot.database.automodsettings.find_one({'guild': member_or_channel.guild.id})
        if doc is None:
            return False

        # Safe access for both dict and schema
        whitelist = doc.get('whitelist', []) if isinstance(doc, dict) else getattr(doc, 'whitelist', [])
        return member_or_channel.id in whitelist

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info('Automod cog loaded.')
        if self.bot.config.perspective_api_key is None:
            logging.warning(
                'Perspective API key not set. AI detection will not work.')

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        try:
            if not message.guild:
                return
                
            doc = await self.bot.database.ai_detection.find_one({'guild': message.guild.id})
            # Safe access for both dict and schema
            enabled = doc.get('enabled') if isinstance(doc, dict) else getattr(doc, 'enabled', False) if doc else False
            if doc is None or enabled is False:
                return
            if message.author.bot:
                return
        except AttributeError:
            return

        # Check whitelist with proper type handling
        author_whitelisted = False
        channel_whitelisted = False
        
        if isinstance(message.author, discord.Member):
            author_whitelisted = await self.check_whitelist(message.author)
        
        if isinstance(message.channel, discord.TextChannel):
            channel_whitelisted = await self.check_whitelist(message.channel)
            
        if author_whitelisted or channel_whitelisted:
            return

        if self.bot.config.perspective_api_key is None:
            return

        detections = await self.ai_detect(message.content, message.guild, doc)
        detections_str = ''

        if detections is None:
            return

        for key, value in detections.items():
            detections_str += f'{key}: {value["summaryScore"]["value"]}\n'

        if len(detections) > 0:
            await message.delete()
            # Safe channel mention handling
            if isinstance(message.channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
                channel_mention = message.channel.mention
            else:
                channel_mention = str(message.channel)
            await message.author.send(f'Your message```{message.content}```in {channel_mention} was deleted due to the following AI detections:\n{detections_str}')
            if message.guild:
                await self.bot.log(message.guild, 'Automod', 'AI Detection (message send)', f'Message from {message.author} was deleted due to the following AI detections:\n{detections_str}\nMessage:\n{message.content}', user=message.guild.me, target=message.author)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        try:
            if not after.guild:
                return
                
            doc = await self.bot.database.ai_detection.find_one({'guild': after.guild.id})
            # Safe access for both dict and schema
            enabled = doc.get('enabled') if isinstance(doc, dict) else getattr(doc, 'enabled', False) if doc else False
            if doc is None or enabled is False:
                return
            if after.author.bot:
                return
        except AttributeError:
            return

        # Check whitelist with proper type handling
        author_whitelisted = False
        channel_whitelisted = False
        
        if isinstance(after.author, discord.Member):
            author_whitelisted = await self.check_whitelist(after.author)
        
        if isinstance(after.channel, discord.TextChannel):
            channel_whitelisted = await self.check_whitelist(after.channel)
            
        if author_whitelisted or channel_whitelisted:
            return

        if self.bot.config.perspective_api_key is None:
            return

        detections = await self.ai_detect(after.content, after.guild, doc)
        detections_str = ''

        if detections is None:
            return

        for key, value in detections.items():
            detections_str += f'{key}: {value["summaryScore"]["value"]}\n'

        if len(detections) > 0:
            await after.delete()
            # Safe channel mention handling
            if isinstance(after.channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
                channel_mention = after.channel.mention
            else:
                channel_mention = str(after.channel)
            await after.author.send(f'Your message```{after.content}```in {channel_mention} was deleted due to the following AI detections:\n{detections_str}')
            if after.guild:
                await self.bot.log(after.guild, 'Automod', 'AI Detection (message edit)', f'Message from {after.author} was deleted due to the following AI detections:\n{detections_str}\nMessage:\n{after.content}', user=after.guild.me, target=after.author)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # Handle nickname changes (AI detection)
        if after.nick is not None and after.nick != before.nick:
            doc = await self.bot.database.automodsettings.find_one({'guild': after.guild.id, 'whitelist': {'$in': [after.id]}})
            if doc is not None:
                return

            try:
                doc = await self.bot.database.ai_detection.find_one({'guild': after.guild.id})
                # Safe access for both dict and schema
                enabled = doc.get('enabled') if isinstance(doc, dict) else getattr(doc, 'enabled', False) if doc else False
                if doc is None or enabled is False:
                    return
                if after.bot:
                    return
            except AttributeError:
                return

            if await self.check_whitelist(after):
                return

            if self.bot.config.perspective_api_key is None:
                return

            detections = await self.ai_detect(after.nick, after.guild, doc)
            detections_str = ''

            if detections is None:
                return

            for key, value in detections.items():
                detections_str += f'{key}: {value["summaryScore"]["value"]}\n'

            if len(detections) > 0:
                await after.edit(nick=before.nick)
                await after.send(f'Your nickname in {after.guild.name} was reset due to the following AI detections:\n{detections_str}\nNickname:\n{after.nick}')
                await self.bot.log(after.guild, 'Automod', 'AI Detection (nickname update)', f'Nickname of {after} was reset due to the following AI detections:\n{detections_str}\nNickname:\n{after.nick}', user=after.guild.me, target=after)

        # Handle role changes (permissions timeout)
        if before.roles != after.roles:
            doc = await self.bot.database.automodsettings.find_one({'guild': after.guild.id})
            if doc is None:
                return

            # Safe access for both dict and schema
            permissions_timeout = doc.get('permissions_timeout') if isinstance(doc, dict) else getattr(doc, 'permissions_timeout', None)
            if permissions_timeout is None:
                return

            # Safe access for whitelist
            permissions_timeout_whitelist = doc.get('permissions_timeout_whitelist', []) if isinstance(doc, dict) else getattr(doc, 'permissions_timeout_whitelist', [])
            if after.id in permissions_timeout_whitelist:
                return

            if after == self.bot.user:
                return

            if after.joined_at is None:
                return

            if (after.joined_at.timestamp() + permissions_timeout) > discord.utils.utcnow().timestamp():
                new_roles = [
                    role for role in after.roles if role not in before.roles]

                roles = set([])

                for role in new_roles:
                    for permission in role.permissions:
                        if not permission[1]:
                            continue

                        if permission[0] in moderation_permissions:
                            roles.add(role)

                    for channel in after.guild.channels:
                        for overwrite in channel.overwrites_for(role):
                            if overwrite[1] is True:
                                if overwrite[0] in moderation_permissions:
                                    roles.add(role)

                await after.remove_roles(*roles)
                if len(roles) > 0:
                    await self.bot.log(after.guild, 'Automod', 'Permissions Timeout',
                                       f'User {after} was removed from role(s) {", ".join(
                                           [role.mention for role in roles])} due to permissions timeout.',
                                       user=after.guild.me, target=after)
                    await after.send(f'In the server {after.guild.name}, you were removed from role(s) {", ".join([role.name for role in roles])} due to permissions timeout.')

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        if not entry.guild or not entry.user or not entry.target:
            return
        
        if not isinstance(entry.target, discord.Member) or not isinstance(entry.user, discord.Member):
            return
            
        target: discord.Member = entry.target
        user: discord.Member = entry.user
        guild: discord.Guild = entry.guild

        if entry.action in AuditLogCheckTypes.moderation_actions:
            doc = await self.bot.database.automodsettings.find_one({'guild': guild.id})
            if doc is None:
                return

            # Safe access for both dict and schema
            permissions_timeout = doc.get('permissions_timeout') if isinstance(doc, dict) else getattr(doc, 'permissions_timeout', None)
            if permissions_timeout is None:
                return

            # Safe access for whitelist
            permissions_timeout_whitelist = doc.get('permissions_timeout_whitelist', []) if isinstance(doc, dict) else getattr(doc, 'permissions_timeout_whitelist', [])
            if user.id in permissions_timeout_whitelist:
                return

            if entry.user == self.bot.user:
                return

            if user.joined_at is None:
                return

            if (user.joined_at.timestamp() + permissions_timeout) > discord.utils.utcnow().timestamp():
                # Find moderation permissions of user
                user_permissions = set([])

                for permissions in user.guild_permissions:
                    if permissions[1] is True:
                        user_permissions.add(permissions[0])

                for role in user.roles:
                    for permissions in role.permissions:
                        if permissions[1] is True:
                            user_permissions.add(permissions[0])

                offending_permissions = [
                    x for x in user_permissions if x in moderation_permissions]

                # Find role(s) that gives permissions
                roles = set([])

                for role in user.roles:
                    for permission in role.permissions:
                        if not permission[1]:
                            continue

                        if permission[0] in offending_permissions:
                            roles.add(role)

                # Look for channel overrides
                for role in user.roles:
                    for channel in guild.channels:
                        for overwrite in channel.overwrites_for(role):
                            if overwrite[1] is True:
                                if overwrite[0] in moderation_permissions:
                                    roles.add(role)

                await user.remove_roles(*roles)
                await self.bot.log(guild, 'Automod', 'Permissions Timeout',
                                   f'User {user} was removed from role(s) {", ".join(
                                       [role.mention for role in roles])} due to permissions timeout.',
                                   user=guild.me, target=user)
                await user.send(f'In the server {guild.name}, you were removed from role(s) {", ".join([role.name for role in roles])} due to permissions timeout.')

                # Try to undo the action
                result = await attempt_undo_audit_log_action(entry, self.bot)
                if result is False:
                    await self.bot.log(guild, 'Automod', 'Permissions Timeout', f'Failed to undo moderation action {entry.action} by {user} on {target}.', user=guild.me, target=user, color=discord.Color.red())
                elif result is None:
                    await self.bot.log(guild, 'Automod', 'Permissions Timeout', f'Partially undone moderation action {entry.action} by {user} on {target}.', user=guild.me, target=user, color=discord.Color.orange())
                elif result is True:
                    await self.bot.log(guild, 'Automod', 'Permissions Timeout', f'Undone moderation action {entry.action} by {user} on {target}.', user=guild.me, target=user, color=discord.Color.green())



    auto_mod = app_commands.Group(name='automod', description='Manage Automod settings',
                                  default_permissions=discord.Permissions(manage_guild=True), guild_only=True)

    @auto_mod.command(name='ai', description='Manage AI automod settings. Recommended to set to 70-80% for best results.')
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def automod(self, interaction: discord.Interaction, enabled: bool | None = None, option: Literal['TOXICITY', 'SEVERE_TOXICITY', 'IDENTITY_ATTACK', 'INSULT', 'PROFANITY', 'THREAT', 'FLIRTATION', 'OBSCENE', 'SPAM'] | None = None, value: int | None = None):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        if enabled is not None:
            doc = await self.bot.database.ai_detection.find_one({'guild': interaction.guild.id})
            if doc is None:
                await self.bot.database.ai_detection.insert_one({'guild': interaction.guild.id, 'enabled': enabled})
                if enabled is False:
                    await interaction.followup.send(f'AI Detection disabled.', ephemeral=True)
                elif enabled is True:
                    await interaction.followup.send(f'AI Detection enabled.', ephemeral=True)

                return
            else:
                if enabled is False:
                    await self.bot.database.ai_detection.update_one({'guild': interaction.guild.id}, {'$set': {'enabled': False}})
                    await interaction.followup.send(f'AI Detection disabled.', ephemeral=True)
                    return
                elif enabled is True:
                    await self.bot.database.ai_detection.update_one({'guild': interaction.guild.id}, {'$set': {'enabled': True}})
                    await interaction.followup.send(f'AI Detection enabled.', ephemeral=True)
                    return

        if option is not None and value is None:
            await interaction.followup.send(f'Invalid arguments. Please provide a value.', ephemeral=True)
            return
        if option is not None and value is not None and (value < 0 or value > 100):
            await interaction.followup.send(f'Invalid value. Value must be between 0 and 100.', ephemeral=True)
            return
        if enabled is None and (option is None or value is None):
            await interaction.followup.send(f'Invalid arguments. Please provide an option and value.', ephemeral=True)
            return
        if option is None and enabled is None and value is None:
            await interaction.followup.send(f'Invalid arguments. Please provide an enabled state, or an option and value.', ephemeral=True)
            return

        if await self.bot.database.ai_detection.find_one({'guild': interaction.guild.id}) is not None:
            await self.bot.database.ai_detection.update_one({'guild': interaction.guild.id}, {'$set': {option: value}})
        else:
            await self.bot.database.ai_detection.insert_one({'guild': interaction.guild.id, option: value})

        await interaction.followup.send(f'`{option}` set to `{value}`', ephemeral=True)

    @auto_mod.command(name='ai_overview', description='View AI automod settings')
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def automod_overview(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        doc = await self.bot.database.ai_detection.find_one({'guild': interaction.guild.id})
        if doc is None:
            await interaction.followup.send(f'AI Detection is disabled.', ephemeral=True)
            return
        embed = discord.Embed(title='AI Detection Overview',
                              description='AI Detection is currently enabled. The following settings are set:', color=discord.Color.green())
        
        # Safe access for both dict and schema
        if isinstance(doc, dict):
            for key, value in doc.items():
                if key == '_id' or key == 'guild':
                    continue
                embed.add_field(name=key, value=value, inline=True)
        else:
            # Handle schema object
            for attr in dir(doc):
                if not attr.startswith('_') and attr != 'guild':
                    value = getattr(doc, attr, None)
                    if value is not None:
                        embed.add_field(name=attr, value=value, inline=True)
        
        await interaction.followup.send(embeds=[embed], ephemeral=True)

    @auto_mod.command(name='log', description='Set the log channel for automod')
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def automod_log(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        if await self.bot.database.automodsettings.find_one({'guild': interaction.guild.id}) is not None:
            await self.bot.database.automodsettings.update_one({'guild': interaction.guild.id}, {'$set': {'log_channel': channel.id}})
        else:
            await self.bot.database.automodsettings.insert_one({'guild': interaction.guild.id, 'log_channel': channel.id})

        await interaction.followup.send(f'Log channel set to {channel.mention}', ephemeral=True)

    @auto_mod.command(name='permissions_timeout', description='Set how long users must be in the server to gain moderation permissions')
    @app_commands.describe(timeout='How long users must be in the server to gain moderation permissions, in seconds')
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    @checks.is_guild_owner()
    async def automod_permissions_timeout(self, interaction: discord.Interaction, timeout: int):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        if await self.bot.database.automodsettings.find_one({'guild': interaction.guild.id}) is not None:
            await self.bot.database.automodsettings.update_one({'guild': interaction.guild.id}, {'$set': {'permissions_timeout': timeout}})
        else:
            await self.bot.database.automodsettings.insert_one({'guild': interaction.guild.id, 'permissions_timeout': timeout})

        await interaction.followup.send(f'Permissions timeout set to {timeout} seconds.', ephemeral=True)

    @auto_mod.command(name='permissions_timeout_whitelist', description='Whitelist a user from the permissions timeout')
    @app_commands.describe(user='The user to whitelist', state='Whether to whitelist or unwhitelist the user')
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @checks.is_guild_owner()
    async def permissions_timeout_whitelist(self, interaction: discord.Interaction, user: discord.Member, state: bool = True):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        doc = await self.bot.database.automodsettings.find_one({'guild': interaction.guild.id})
        if doc is None:
            await self.bot.database.automodsettings.insert_one({'guild': interaction.guild.id, 'permissions_timeout_whitelist': []})
            doc = await self.bot.database.automodsettings.find_one({'guild': interaction.guild.id})

        if state is True:
            # Safe access for both dict and schema
            whitelist = doc.get('permissions_timeout_whitelist', []) if isinstance(doc, dict) else getattr(doc, 'permissions_timeout_whitelist', [])
            if user.id in whitelist:
                await interaction.followup.send(f'{user.mention} is already whitelisted.', ephemeral=True)
                return
            
            whitelist.append(user.id)
            await self.bot.database.automodsettings.update_one({'guild': interaction.guild.id}, {'$set': {'permissions_timeout_whitelist': whitelist}})
            await interaction.followup.send(f'{user.mention} whitelisted.', ephemeral=True)
        elif state is False:
            # Safe access for both dict and schema
            whitelist = doc.get('permissions_timeout_whitelist', []) if isinstance(doc, dict) else getattr(doc, 'permissions_timeout_whitelist', [])
            if user.id not in whitelist:
                await interaction.followup.send(f'{user.mention} is not whitelisted.', ephemeral=True)
                return
            
            whitelist.remove(user.id)
            await self.bot.database.automodsettings.update_one({'guild': interaction.guild.id}, {'$set': {'permissions_timeout_whitelist': whitelist}})
            await interaction.followup.send(f'{user.mention} unwhitelisted.', ephemeral=True)

    @auto_mod.command(name="whitelist", description="Whitelist a user or channel from automod")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    @checks.is_guild_owner()
    async def whitelist(self, interaction: discord.Interaction, state: bool = True, user: discord.User | None = None, channel: discord.TextChannel | None = None):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        if user is None and channel is None:
            await interaction.followup.send(f'Invalid arguments. Please provide a user or channel.', ephemeral=True)
            return
        if user is not None and channel is not None:
            await interaction.followup.send(f'Invalid arguments. Please provide a user or channel, not both.', ephemeral=True)
            return

        user_or_channel = user if user is not None else channel
        if user_or_channel is None:
            return
            
        doc = await self.bot.database.automodsettings.find_one({'guild': interaction.guild.id})
        if doc is None:
            await self.bot.database.automodsettings.insert_one({'guild': interaction.guild.id, 'whitelist': []})
            doc = await self.bot.database.automodsettings.find_one({'guild': interaction.guild.id})

        # Safe access for both dict and schema
        whitelist = doc.get('whitelist', []) if isinstance(doc, dict) else getattr(doc, 'whitelist', [])

        if state:
            if user_or_channel.id in whitelist:
                await interaction.followup.send(f'{user_or_channel.mention} is already whitelisted.', ephemeral=True)
                return
            
            whitelist.append(user_or_channel.id)
        else:
            if user_or_channel.id not in whitelist:
                await interaction.followup.send(f'{user_or_channel.mention} is not whitelisted.', ephemeral=True)
                return
            
            whitelist.remove(user_or_channel.id)

        await self.bot.database.automodsettings.update_one({'guild': interaction.guild.id}, {'$set': {'whitelist': whitelist}})

        if state is True:
            await interaction.followup.send(f'{user_or_channel.mention} whitelisted.', ephemeral=True)
        else:
            await interaction.followup.send(f'{user_or_channel.mention} unwhitelisted.', ephemeral=True)


async def setup(bot: KidneyBot):
    automod = Automod(bot)
    if bot.config.perspective_api_key is None:
        # Disable AI commands if no API key
        automod.auto_mod.remove_command('ai')
        automod.auto_mod.remove_command('ai_overview')
    await bot.add_cog(automod)
