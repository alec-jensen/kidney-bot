# This cog creates all ActiveGuard features
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import datetime
import time
import discord
from discord.ext import commands
from discord import app_commands
from typing import Literal
import uuid
import logging
import asyncio

from utils.database import Schemas, ReportsDocument, ScammerListDocument, ActiveGuardSettingsDocument
from utils.kidney_bot import KidneyBot, KBMember
from typing import Optional, cast


class ReportView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Accept', style=discord.ButtonStyle.green, custom_id='report:accept')
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.message or not interaction.message.embeds:
            await interaction.response.send_message('Error: Unable to access report information.', ephemeral=True)
            return
        
        footer_text = interaction.message.embeds[0].footer.text
        if not footer_text:
            await interaction.response.send_message('Error: Report ID not found.', ephemeral=True)
            return
        
        report_id = footer_text.split('`')[1]
        bot = cast(KidneyBot, interaction.client)
        report = await bot.database.reports.find_one({"report_id": report_id}, Schemas.Reports)
        if report is None:
            await interaction.response.send_message('Report not found.', ephemeral=True)
            return
        
        # Handle both dict and schema access patterns
        reported_user = report.get('reported_user') if isinstance(report, dict) else getattr(report, 'reported_user', None)
        reporter = report.get('reporter') if isinstance(report, dict) else getattr(report, 'reporter', None)
        reported_user_name = report.get('reported_user_name') if isinstance(report, dict) else getattr(report, 'reported_user_name', None)
        reason = report.get('reason') if isinstance(report, dict) else getattr(report, 'reason', None)
        report_status = report.get('report_status') if isinstance(report, dict) else getattr(report, 'report_status', None)
        
        if report_status is None or bot.config.is_owner(interaction.user.id):
            await bot.database.reports.update_one({"report_id": report_id},
                                                       {"$set": {"report_status": "accepted", "handled_by": interaction.user.id}})

        doc = await bot.database.scammer_list.find_one({"user": reported_user}, Schemas.ScammerList)
        if doc is None and reported_user is not None:
            await bot.database.scammer_list.insert_one(Schemas.ScammerList(
                user=reported_user,
                time=int(time.time()),
                reason=reason or "No reason provided",
            ))

        # Send notifications safely
        if reporter is not None:
            try:
                user = bot.get_user(reporter)
                if user:
                    await user.send(f"Your report on **{reported_user_name or 'Unknown User'}** has been accepted.")
            except:
                pass
        
        if reported_user is not None:
            try:
                user = bot.get_user(reported_user)
                if user:
                    await user.send("You have been added to kidney bot's scammer blacklist. You can appeal this in our support server. https://discord.com/invite/TsuZCbz5KD")
            except:
                pass

        embed = interaction.message.embeds[0]
        embed.add_field(name='✅', value=f'Accepted by {interaction.user}', inline=False)
        await interaction.message.edit(embed=embed)
        await interaction.response.send_message('Report accepted.', ephemeral=True)

        # Update other reports for the same user
        if bot.config.report_channel is not None:
            try:
                channel = bot.get_channel(bot.config.report_channel)
                if channel and isinstance(channel, (discord.TextChannel, discord.Thread)):
                    async for message in channel.history(limit=None):
                        if message.embeds and message.embeds[0].footer and message.embeds[0].footer.text:
                            try:
                                other_report_id = message.embeds[0].footer.text.split('`')[1]
                                other_doc = await bot.database.reports.find_one({"report_id": other_report_id}, Schemas.Reports)
                                if other_doc is not None:
                                    other_reported_user = other_doc.get('reported_user') if isinstance(other_doc, dict) else getattr(other_doc, 'reported_user', None)
                                    other_report_status = other_doc.get('report_status') if isinstance(other_doc, dict) else getattr(other_doc, 'report_status', None)
                                    
                                    if other_reported_user == reported_user and other_report_status is None:
                                        embed = message.embeds[0]
                                        embed.add_field(name='❕', value=f'User is on blacklist.', inline=False)
                                        await message.edit(embed=embed)
                            except (IndexError, AttributeError):
                                continue
            except:
                pass

        # Ban user from all guilds
        if reported_user is not None:
            async for guild in bot.fetch_guilds():
                try:
                    await guild.ban(discord.Object(id=reported_user))
                except:
                    pass

    @discord.ui.button(label='Deny', style=discord.ButtonStyle.red, custom_id='report:deny')
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.message or not interaction.message.embeds:
            await interaction.response.send_message('Error: Unable to access report information.', ephemeral=True)
            return
        
        footer_text = interaction.message.embeds[0].footer.text
        if not footer_text:
            await interaction.response.send_message('Error: Report ID not found.', ephemeral=True)
            return
        
        report_id = footer_text.split('`')[1]
        bot = cast(KidneyBot, interaction.client)
        report = await bot.database.reports.find_one({"report_id": report_id}, Schemas.Reports)
        if report is None:
            await interaction.response.send_message('Report not found.', ephemeral=True)
            return
        
        # Handle both dict and schema access patterns
        reported_user = report.get('reported_user') if isinstance(report, dict) else getattr(report, 'reported_user', None)
        reporter = report.get('reporter') if isinstance(report, dict) else getattr(report, 'reporter', None)
        reported_user_name = report.get('reported_user_name') if isinstance(report, dict) else getattr(report, 'reported_user_name', None)
        report_status = report.get('report_status') if isinstance(report, dict) else getattr(report, 'report_status', None)
        
        if report_status is None or bot.config.is_owner(interaction.user.id):
            await bot.database.reports.update_one({"report_id": report_id},
                                                       {"$set": {"report_status": "denied", "handled_by": interaction.user.id}})

        doc = await bot.database.scammer_list.find_one({"user": reported_user}, Schemas.ScammerList)
        if doc is not None and reported_user is not None:
            await bot.database.scammer_list.delete_one(doc)
            async for guild in bot.fetch_guilds():
                try:
                    await guild.unban(discord.Object(id=reported_user))
                except:
                    pass

        # Send notification safely
        if reporter is not None:
            try:
                user = bot.get_user(reporter)
                if user:
                    await user.send(f"Your report on **{reported_user_name or 'Unknown User'}** has been denied.")
            except:
                pass
        
        embed = interaction.message.embeds[0]
        embed.add_field(name='❌', value=f'Denied by {interaction.user}', inline=False)
        await interaction.message.edit(embed=embed)
        await interaction.response.send_message('Report denied.', ephemeral=True)


class ActiveGuard(commands.Cog):

    def __init__(self, bot):
        self.bot: KidneyBot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info('ActiveGuard cog loaded.')

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.channel.type is discord.ChannelType.private or message.author.bot:
            return
        
        if not message.guild:
            return
        
        doc = asyncio.create_task(self.bot.database.active_guard_settings.find_one({"guild_id": message.guild.id}))
        user_doc = asyncio.create_task(self.bot.database.scammer_list.find_one({"user": message.author.id}))

        member = message.author
        doc = await doc

        # Handle both dict and schema access patterns
        if doc is not None:
            block_spammers = doc.get('block_known_spammers') if isinstance(doc, dict) else getattr(doc, 'block_known_spammers', False)
            if block_spammers is True:
                user_result = await user_doc
                if user_result is not None and isinstance(member, discord.Member):
                    try:
                        await member.send(f'You have been banned from {message.guild.name} for being on the global blacklist. You can appeal this in our support server. https://discord.com/invite/TsuZCbz5KD')
                    except:
                        pass
                    try:
                        await member.ban(reason="User is on global blacklist.")
                    except:
                        pass
                    try:
                        await self.bot.log(message.guild, 'Automod', 'Remove blacklisted user', 'User is on global blacklist. Blocking blacklisted users is enabled.', user=member)
                    except:
                        pass

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if after.author.bot or after.channel.type is discord.ChannelType.private:
            return
        
        if not after.guild:
            return
        
        doc = asyncio.create_task(self.bot.database.active_guard_settings.find_one({"guild_id": after.guild.id}))
        user_doc = asyncio.create_task(self.bot.database.scammer_list.find_one({"user": after.author.id}))

        member = after.author
        doc = await doc

        # Handle both dict and schema access patterns
        if doc is not None:
            block_spammers = doc.get('block_known_spammers') if isinstance(doc, dict) else getattr(doc, 'block_known_spammers', False)
            if block_spammers is True:
                user_result = await user_doc
                if user_result is not None and isinstance(member, discord.Member):
                    try:
                        await member.send(f'You have been banned from {after.guild.name} for being on the global blacklist. You can appeal this in our support server. https://discord.com/invite/TsuZCbz5KD')
                    except:
                        pass
                    try:
                        await member.ban(reason="User is on global blacklist.")
                    except:
                        pass
                    try:
                        await self.bot.log(after.guild, 'Automod', 'Remove blacklisted user', 'User is on global blacklist. Blocking blacklisted users is enabled.', user=member)
                    except:
                        pass
    
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        user_doc = asyncio.create_task(self.bot.database.scammer_list.find_one({"user": after.id}))
        doc = await self.bot.database.active_guard_settings.find_one({"guild_id": before.guild.id})
        
        # Handle both dict and schema access patterns
        if doc is not None:
            block_spammers = doc.get('block_known_spammers') if isinstance(doc, dict) else getattr(doc, 'block_known_spammers', False)
            if block_spammers is True:
                user_result = await user_doc
                if user_result is not None:
                    try:
                        await after.send(f'You have been banned from {before.guild.name} for being on the global blacklist. You can appeal this in our support server. https://discord.com/invite/TsuZCbz5KD')
                    except:
                        pass
                    try:
                        await after.ban(reason="User is on global blacklist.")
                    except:
                        pass
                    try:
                        await self.bot.log(before.guild, 'Automod', 'Remove blacklisted user', 'User is on global blacklist. Blocking blacklisted users is enabled.', user=after)
                    except:
                        pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        user_doc = asyncio.create_task(self.bot.database.scammer_list.find_one({"user": member.id}))
        doc = await self.bot.database.active_guard_settings.find_one({"guild_id": member.guild.id})
        
        # Handle both dict and schema access patterns
        if doc is not None:
            block_spammers = doc.get('block_known_spammers') if isinstance(doc, dict) else getattr(doc, 'block_known_spammers', False)
            if block_spammers is True:
                user_result = await user_doc
                if user_result is not None:
                    try:
                        await member.send(f'You have been banned from {member.guild.name} for being on the global blacklist. You can appeal this in our support server. https://discord.com/invite/TsuZCbz5KD')
                    except:
                        pass
                    try:
                        await member.ban(reason="User is on global blacklist.")
                    except:
                        pass
                    try:
                        await self.bot.log(member.guild, 'Automod', 'Remove blacklisted user', 'User is on global blacklist. Blocking blacklisted users is enabled.', user=member)
                    except:
                        pass

    @commands.Cog.listener()
    async def on_typing(self, channel: discord.TextChannel, user: discord.User, when: datetime.datetime):
        # Skip if channel doesn't have a guild (DMs, etc.)
        if not hasattr(channel, 'guild') or not channel.guild:
            return
            
        doc = await self.bot.database.active_guard_settings.find_one({"guild_id": channel.guild.id})
        
        # Handle both dict and schema access patterns
        if doc is not None:
            block_spammers = doc.get('block_known_spammers') if isinstance(doc, dict) else getattr(doc, 'block_known_spammers', False)
            if block_spammers is True:
                scammer_doc = await self.bot.database.scammer_list.find_one({"user": user.id})
                if scammer_doc is not None:
                    # Get the member object to ban them
                    try:
                        member = channel.guild.get_member(user.id)
                        if member:
                            try:
                                await member.send(f'You have been banned from {channel.guild.name} for being on the global blacklist. You can appeal this in our support server. https://discord.com/invite/TsuZCbz5KD')
                            except:
                                pass
                            try:
                                await member.ban(reason="User is on global blacklist.")
                            except:
                                pass
                            try:
                                await self.bot.log(channel.guild, 'Automod', 'Remove blacklisted user', 'User is on global blacklist. Blocking blacklisted users is enabled.', user=member)
                            except:
                                pass
                    except:
                        pass

    active_guard = app_commands.Group(name='activeguard', description='Manage ActiveGuard settings',
                                      default_permissions=discord.Permissions(manage_guild=True), guild_only=True)

    @active_guard.command(name='block_spammers', description='Should ActiveGuard block known spammers?')
    async def block_known_spammers(self, interaction: discord.Interaction, state: Literal['on', 'off']):
        await interaction.response.defer(ephemeral=True)
        
        if not interaction.guild:
            await interaction.followup.send('This command can only be used in a server.', ephemeral=True)
            return
        
        # Check if the guild has a document in the database, if not create one
        if await self.bot.database.active_guard_settings.find_one({"guild_id": interaction.guild.id}) is None:
            await self.bot.database.active_guard_settings.insert_one({"guild_id": interaction.guild.id})

        if state == 'on':
            await self.bot.database.active_guard_settings.update_one({"guild_id": interaction.guild.id},
                                                      {"$set": {"block_known_spammers": True}})
            await interaction.followup.send('ActiveGuard will now block known spammers.', ephemeral=True)
        else:
            await self.bot.database.active_guard_settings.update_one({"guild_id": interaction.guild.id},
                                                      {"$set": {"block_known_spammers": False}})
            await interaction.followup.send('ActiveGuard will no longer block known spammers.', ephemeral=True)

    @app_commands.command(name='report', description='report scammers')
    async def report_command(self, interaction: discord.Interaction, user: discord.User, reason: str,
                             message_id: Optional[int] = None):
        await interaction.response.defer(ephemeral=True)
        report_id = uuid.uuid4()
        
        message = None
        if message_id is not None and interaction.channel and isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
            try:
                message = await interaction.channel.fetch_message(message_id)
                if message and message.author != user:
                    await interaction.followup.send('The provided message isn\'t from the user whom you are trying to report!', ephemeral=True)
                    return
            except:
                await interaction.followup.send('Could not fetch the specified message.', ephemeral=True)
                return
                
        doc = await self.bot.database.scammer_list.find_one({"user": user.id})
        if doc is not None:
            await interaction.followup.send('User already blacklisted.', ephemeral=True)
            return
            
        embed = discord.Embed(title=f'{interaction.user} has submitted a report!', color=discord.Color.red())
        embed.add_field(name=f'Suspect: {user.name}#{user.discriminator}({user.id})',
                        value=f'Reason: ```{reason}```' +
                              (f'\nReported message: ```{message.content}```\n'
                               f'Message attachments: {message.attachments}' if message is not None else ''))
        embed.set_footer(text=f'Report ID: `{report_id}`')
        
        # Send report safely
        if self.bot.config.report_channel is not None:
            try:
                channel = self.bot.get_channel(self.bot.config.report_channel)
                if channel and isinstance(channel, (discord.TextChannel, discord.Thread)):
                    await channel.send(embed=embed, view=ReportView())
                else:
                    await interaction.followup.send('Error: Could not send report to the configured channel.', ephemeral=True)
                    return
            except:
                await interaction.followup.send('Error: Could not send report to the configured channel.', ephemeral=True)
                return
        else:
            await interaction.followup.send('Error: No report channel configured.', ephemeral=True)
            return
            
        await self.bot.database.reports.insert_one({
            "report_id": str(report_id),
            "reporter": interaction.user.id,
            "time_reported": time.time(),
            "reported_user": user.id,
            "reported_user_name": str(user),
            "reason": reason,
            "attached_message": message.content if message is not None else None,
            "attached_message_attachments": message.attachments if message is not None else None,
            "report_status": None,
            "handled_by": None
        })
        await interaction.followup.send('Report submitted! Thank you.', ephemeral=True)


async def setup(bot):
    await bot.add_cog(ActiveGuard(bot))
