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
import utils.permission_checks as permission_checks

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

    async def ai_detect(self, content: str, guild: discord.Guild, doc: dict = None) -> dict:
        if self.bot.config.perspective_api_key is None:
            return

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
                    doc = await self.bot.database.ai_detection.find_one({'guild': guild.id})
                    if doc is None:
                        return None

                detections = {}
                if resp_json.get('attributeScores') is None:
                    return None
                for key, value in resp_json['attributeScores'].items():
                    # deepcode ignore AttributeLoadOnNone: this warning is incorrect
                    if value['summaryScore']['value'] > doc.get(key, 60) / 100:
                        detections[key] = value

                return detections

    async def check_whitelist(self, user_or_channel: discord.User or discord.TextChannel):
        doc = await self.bot.database.automodsettings.find_one({'guild': user_or_channel.guild.id})
        if doc is None:
            return False

        return user_or_channel.id in doc.get('whitelist', [])

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info('Automod cog loaded.')
        if self.bot.config.perspective_api_key is None:
            logging.warning(
                'Perspective API key not set. AI detection will not work.')

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return

        doc = await self.bot.database.audit_log_undo.find_one({'type': 'restore_on_join', 'guild_id': member.guild.id, 'user_id': member.id})
        if doc is not None:
            member_roles = []
            for role_id in doc.get('roles'):
                member_roles.append(member.guild.get_role(role_id))

            await member.add_roles(*member_roles, reason='Restored roles from moderation action undo.')
            await member.edit(nick=doc.get('nick'), reason='Restored nickname from moderation action undo.')

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        try:
            doc = await self.bot.database.ai_detection.find_one({'guild': message.guild.id})
            if doc is None or doc.get('enabled') is False:
                return
            if message.author.bot:
                return
        except AttributeError:
            return

        if await self.check_whitelist(message.author) or await self.check_whitelist(message.channel):
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
            await message.author.send(f'Your message in {message.channel.mention} was deleted due to the following AI detections:\n{detections_str}')
            await self.bot.log(message.guild, 'Automod', 'AI Detection (message send)', f'Message from {message.author} was deleted due to the following AI detections:\n{detections_str}', user=message.guild.me, target=message.author)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        try:
            doc = await self.bot.database.ai_detection.find_one({'guild': after.guild.id})
            if doc is None or doc.get('enabled') is False:
                return
            if after.author.bot:
                return
        except AttributeError:
            return

        if await self.check_whitelist(after.author) or await self.check_whitelist(after.channel):
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
            await after.author.send(f'Your message in {after.channel.mention} was deleted due to the following AI detections:\n{detections_str}')
            await self.bot.log(after.guild, 'Automod', 'AI Detection (message edit)', f'Message from {after.author} was deleted due to the following AI detections:\n{detections_str}', user=after.guild.me, target=after.author)

    @commands.Cog.listener()
    async def on_member_update(self, before, after: discord.Member):
        if after.nick is None:
            return
        if after.nick == before.nick:
            return

        doc = await self.bot.database.automodsettings.find_one({'guild': after.guild.id, 'whitelist': {'$in': [after.id]}})
        if doc is not None:
            return

        try:
            doc = await self.bot.database.ai_detection.find_one({'guild': after.guild.id})
            if doc is None or doc.get('enabled') is False:
                return
            if after.author.bot:
                return
        except AttributeError:
            return

        if await self.check_whitelist(after.author):
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
            await after.edit(nick=before.nick)
            await after.member.send(f'Your nickname was reset due to AI detections:\n{detections_str}')
            await self.bot.log(after.guild, 'Automod', 'AI Detection (nickname update)', f'Message from {after.author} was deleted due to the following AI detections:\n{detections_str}', user=after.guild.me, target=after.author)

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        target: discord.Member = entry.target
        user: discord.Member = entry.user
        guild: discord.Guild = entry.guild

        if entry.action in AuditLogCheckTypes.moderation_actions:
            doc = await self.bot.database.automodsettings.find_one({'guild': guild.id})
            if doc is None:
                return

            if doc.get('permissions_timeout') is None:
                return

            if user.id in doc.get('permissions_timeout_whitelist', []):
                return

            if entry.user == self.bot.user:
                return

            if (user.joined_at.timestamp() + doc.get('permissions_timeout')) > discord.utils.utcnow().timestamp():
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
                                   f'User {user} was removed from role(s) {", ".join([role.mention for role in roles])} due to permissions timeout.',
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

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.roles != after.roles:
            doc = await self.bot.database.automodsettings.find_one({'guild': after.guild.id})
            if doc is None:
                return

            if doc.get('permissions_timeout') is None:
                return

            if after.id in doc.get('permissions_timeout_whitelist', []):
                return

            if after == self.bot.user:
                return

            if (after.joined_at.timestamp() + doc.get('permissions_timeout')) > discord.utils.utcnow().timestamp():
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
                                       f'User {after} was removed from role(s) {", ".join([role.mention for role in roles])} due to permissions timeout.',
                                       user=after.guild.me, target=after)
                    await after.send(f'In the server {after.guild.name}, you were removed from role(s) {", ".join([role.name for role in roles])} due to permissions timeout.')

    auto_mod = app_commands.Group(name='automod', description='Manage Automod settings',
                                  default_permissions=discord.Permissions(manage_guild=True))

    @auto_mod.command(name='ai', description='Manage AI automod settings. Recommended to set to 70-80% for best results.')
    @app_commands.default_permissions(manage_guild=True)
    async def automod(self, interaction: discord.Interaction, enabled: bool = None, option: Literal['TOXICITY', 'SEVERE_TOXICITY', 'IDENTITY_ATTACK', 'INSULT', 'PROFANITY', 'THREAT', 'FLIRTATION', 'OBSCENE', 'SPAM'] = None, value: int = None):
        if enabled is not None:
            doc = await self.bot.database.ai_detection.find_one({'guild': interaction.guild.id})
            if doc is None:
                await self.bot.database.ai_detection.insert_one({'guild': interaction.guild.id, 'enabled': enabled})
                if enabled is False:
                    await interaction.response.send_message(f'AI Detection disabled.', ephemeral=True)
                elif enabled is True:
                    await interaction.response.send_message(f'AI Detection enabled.', ephemeral=True)

                return
            else:
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
    @app_commands.default_permissions(manage_guild=True)
    async def automod_overview(self, interaction: discord.Interaction):
        doc = await self.bot.database.ai_detection.find_one({'guild': interaction.guild.id})
        if doc is None:
            await interaction.response.send_message(f'AI Detection is disabled.', ephemeral=True)
            return
        embed = discord.Embed(title='AI Detection Overview',
                              description='AI Detection is currently enabled. The following settings are set:', color=discord.Color.green())
        for key, value in doc.items():
            if key == '_id' or key == 'guild':
                continue
            embed.add_field(name=key, value=value, inline=True)
        await interaction.response.send_message(embeds=[embed], ephemeral=True)

    @auto_mod.command(name='log', description='Set the log channel for automod')
    @app_commands.default_permissions(manage_guild=True)
    async def automod_log(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if await self.bot.database.automodsettings.find_one({'guild': interaction.guild.id}) is not None:
            await self.bot.database.automodsettings.update_one({'guild': interaction.guild.id}, {'$set': {'log_channel': channel.id}})
        else:
            await self.bot.database.automodsettings.insert_one({'guild': interaction.guild.id, 'log_channel': channel.id})

        await interaction.response.send_message(f'Log channel set to {channel.mention}', ephemeral=True)

    @auto_mod.command(name='permissions_timeout', description='Set how long users must be in the server to gain moderation permissions')
    @app_commands.describe(timeout='How long users must be in the server to gain moderation permissions, in seconds')
    @app_commands.default_permissions(manage_guild=True)
    @permission_checks.is_guild_owner()
    async def automod_permissions_timeout(self, interaction: discord.Interaction, timeout: int):
        if await self.bot.database.automodsettings.find_one({'guild': interaction.guild.id}) is not None:
            await self.bot.database.automodsettings.update_one({'guild': interaction.guild.id}, {'$set': {'permissions_timeout': timeout}})
        else:
            await self.bot.database.automodsettings.insert_one({'guild': interaction.guild.id, 'permissions_timeout': timeout})

        await interaction.response.send_message(f'Permissions timeout set to {timeout} seconds.', ephemeral=True)

    @auto_mod.command(name='permissions_timeout_whitelist', description='Whitelist a user from the permissions timeout')
    @app_commands.describe(user='The user to whitelist', state='Whether to whitelist or unwhitelist the user')
    @app_commands.default_permissions(administrator=True)
    @permission_checks.is_guild_owner()
    async def permissions_timeout_whitelist(self, interaction: discord.Interaction, user: discord.Member, state: bool = True):
        doc = await self.bot.database.automodsettings.find_one({'guild': interaction.guild.id})
        if doc is None:
            await self.bot.database.automodsettings.insert_one({'guild': interaction.guild.id, 'permissions_timeout_whitelist': []})
            doc = await self.bot.database.automodsettings.find_one({'guild': interaction.guild.id})

        if state is True:
            if user.id in doc.get('permissions_timeout_whitelist', []):
                await interaction.response.send_message(f'{user.mention} is already whitelisted.', ephemeral=True)
                return
            doc['permissions_timeout_whitelist'] = doc.get(
                'permissions_timeout_whitelist', [])
            doc['permissions_timeout_whitelist'].append(user.id)
            await self.bot.database.automodsettings.update_one({'guild': interaction.guild.id}, {'$set': {'permissions_timeout_whitelist': doc['permissions_timeout_whitelist']}})
            await interaction.response.send_message(f'{user.mention} whitelisted.', ephemeral=True)
        elif state is False:
            if user.id not in doc.get('permissions_timeout_whitelist', []):
                await interaction.response.send_message(f'{user.mention} is not whitelisted.', ephemeral=True)
                return
            doc['permissions_timeout_whitelist'].remove(user.id)
            await self.bot.database.automodsettings.update_one({'guild': interaction.guild.id}, {'$set': {'permissions_timeout_whitelist': doc['permissions_timeout_whitelist']}})
            await interaction.response.send_message(f'{user.mention} unwhitelisted.', ephemeral=True)

    @auto_mod.command(name="whitelist", description="Whitelist a user or channel from automod")
    @app_commands.default_permissions(manage_guild=True)
    async def whitelist(self, interaction: discord.Interaction, state: bool = True, user: discord.User = None, channel: discord.TextChannel = None):
        if user is None and channel is None:
            await interaction.response.send_message(f'Invalid arguments. Please provide a user or channel.', ephemeral=True)
            return
        if user is not None and channel is not None:
            await interaction.response.send_message(f'Invalid arguments. Please provide a user or channel, not both.', ephemeral=True)
            return

        user_or_channel = user if user is not None else channel
        doc = await self.bot.database.automodsettings.find_one({'guild': interaction.guild.id})
        if doc is None:
            await self.bot.database.automodsettings.insert_one({'guild': interaction.guild.id, 'whitelist': []})
            doc = await self.bot.database.automodsettings.find_one({'guild': interaction.guild.id})

        if state is True:
            if user_or_channel.id in doc.get('whitelist', []):
                await interaction.response.send_message(f'{user_or_channel.mention} is already whitelisted.', ephemeral=True)
                return
            doc['whitelist'] = [] if doc.get(
                'whitelist') is None else doc.get('whitelist')
            doc['whitelist'].append(user_or_channel.id)
            await interaction.response.send_message(f'{user_or_channel.mention} whitelisted.', ephemeral=True)
        else:
            if user_or_channel.id not in doc.get('whitelist', []):
                await interaction.response.send_message(f'{user_or_channel.mention} is not whitelisted.', ephemeral=True)
                return
            doc['whitelist'].remove(user_or_channel.id)
            await interaction.response.send_message(f'{user_or_channel.mention} unwhitelisted.', ephemeral=True)

        await self.bot.database.automodsettings.update_one({'guild': interaction.guild.id}, {'$set': {'whitelist': doc['whitelist']}})


async def setup(bot):
    automod = Automod(bot)
    if bot.config.perspective_api_key is None:
        automod.auto_mod = None
    await bot.add_cog(automod)
