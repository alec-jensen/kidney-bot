# This cog creates all moderation commands.
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import discord
from discord.ext import commands
from discord import app_commands
from datetime import timedelta
import humanize
import logging
from typing import Literal, Optional, cast
import asyncio
from uuid import uuid4

from utils.kidney_bot import KidneyBot
from utils.database import Schemas
from utils.types import AnyUser
from utils.misc import ordinal


time_convert = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800
}

items_per_page = 5

class PageDropdown(discord.ui.Select):
    def __init__(self, num_pages: int):
        self.num_pages = num_pages
        options = [discord.SelectOption(label=str(i+1), value=str(i+1)) for i in range(self.num_pages)]
        super().__init__(placeholder='Select a page...', min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not self.view or not isinstance(self.view, WarningsView):
            return
        view = self.view
        view.page = int(self.values[0]) - 1
        await view.update()
        await interaction.response.defer()

class WarningsView(discord.ui.View):
    def __init__(self, bot: KidneyBot, target: AnyUser):
        self.bot = bot
        self.target = target
        super().__init__()
        self.page = 0
        self.warns: list = []
        self.num_pages = 0
        self.message: Optional[discord.Message] = None
    
    async def async_init(self):
        # Only Members have guild attribute, check if target is a Member
        if not isinstance(self.target, discord.Member):
            self.num_pages = 0
            self.warns = []
            self.add_item(discord.ui.Button(label='No warnings - User not in guild', style=discord.ButtonStyle.secondary, disabled=True))
            return
            
        doc = await self.bot.database.warnings.find_one(Schemas.WarnSchema(self.target.id, self.target.guild.id), Schemas.WarnSchema)
        if doc is None:
            self.num_pages = 0
            self.warns = []
            self.add_item(discord.ui.Button(label='No warnings', style=discord.ButtonStyle.secondary, disabled=True))
            return

        # Handle both dict and schema access patterns
        warns_data = doc.get('warns') if isinstance(doc, dict) else getattr(doc, 'warns', [])
        if warns_data is None:
            warns_data = []
            
        self.num_pages = (len(warns_data) + items_per_page - 1) // items_per_page
        self.warns = warns_data

        self.add_item(PageDropdown(self.num_pages))

        self.message = None

    @discord.ui.button(label='Back', style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page == 0:
            return
        self.page -= 1
        await self.update()
        await interaction.response.defer()

    @discord.ui.button(label='Next', style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page == self.num_pages - 1:
            return
        self.page += 1
        await self.update()
        await interaction.response.defer()

    async def update(self):
        next_button = discord.utils.get(self.children, label='Next')
        back_button = discord.utils.get(self.children, label='Back')
        
        if isinstance(back_button, discord.ui.Button):
            if self.page == 0:
                back_button.disabled = True
            else:
                back_button.disabled = False
                
        if isinstance(next_button, discord.ui.Button):
            if self.page == self.num_pages - 1:
                next_button.disabled = True
            else:
                next_button.disabled = False
        
        embed = discord.Embed(title=f"Warnings for {self.target}", color=discord.Color.red())
        embed.add_field(name="Total warnings", value=len(self.warns), inline=False)
        for i in range(self.page * items_per_page, (self.page + 1) * items_per_page):
            if i >= len(self.warns):
                break
            item = self.warns[i]
            embed.add_field(name=f"Warn ID: {item['id']}", value=f"Reason: {item['reason']}\
                            \nModerator: {(await self.bot.fetch_user(item['moderator'])).mention}\
                            \nTimestamp: <t:{item['timestamp']}>", inline=False)
        if len(embed.fields) == 0:
            embed.add_field(name="No warnings", value="This user has no warnings", inline=False)
        embed.set_footer(text=f"Page {self.page + 1}/{self.num_pages}")
        
        if self.message:
            await self.message.edit(embed=embed, view=self)

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot: KidneyBot = bot

    async def permissionHierarchyCheck(self, user: discord.Member, target: discord.Member) -> bool | None:
        logging.debug(
            f'Checking permission hierarchy for {user} and {target}.')
        if target.top_role >= user.top_role:
            if user.guild.owner == user:
                return True
            else:
                return False
        elif target.top_role <= user.top_role:
            return True

    async def convert_time_to_seconds(self, time: str):
        times = []
        current = ""
        for char in time:
            current += char
            if char.isalpha():
                times.append(current)
                current = ""

        if current != "":
            return False

        seconds = 0
        for time in times:
            seconds += int(time[:-1]) * time_convert[time[-1]]

        return seconds

    async def get_ephemeral_messages(self, guild: discord.Guild | None = None, user: discord.User | discord.Member | None = None) -> bool:
        if guild is None and user is None:
            raise ValueError('guild and user cannot both be None')
        
        if guild is not None:
            doc: Schemas.GuildConfig = await self.bot.database.guild_config.find_one(Schemas.GuildConfig(guild.id), Schemas.GuildConfig) # type: ignore
            if doc is not None:
                if doc.ephemeral_setting_overpowers_user_setting or user is None:
                    return bool(doc.ephemeral_moderation_messages)
            
        if user is not None:
            doc2: Schemas.UserConfig = await self.bot.database.user_config.find_one(Schemas.UserConfig(user.id), Schemas.UserConfig) # type: ignore
            if doc2 is not None:
                return bool(doc2.ephemeral_moderation_messages)

        return True

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info('Moderation cog loaded.')

    ephemeral_messages = app_commands.Group(name='ephemeral_messages', description="Configure whether moderation messages are ephemeral or not")

    @ephemeral_messages.command(name='guild', description="Configure whether moderation messages are ephemeral or not for the guild")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def ephemeral_messages_guild(self, interaction: discord.Interaction, ephemeral: Literal["Yes", "No"]):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
            
        ephemeralB = ephemeral == "Yes"
        await interaction.response.defer(ephemeral=True)
        await self.bot.database.guild_config.update_one(Schemas.GuildConfig(interaction.guild.id), {"$set": {"ephemeral_moderation_messages": ephemeralB}}, upsert=True)

        await interaction.followup.send(f"Moderation messages are now ephemeral: {ephemeral}", ephemeral=True)

    @ephemeral_messages.command(name='force_guild_setting', description="Configure whether guild setting overpowers user setting")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def ephemeral_messages_force_guild_setting(self, interaction: discord.Interaction, force: Literal["Yes", "No"]):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
            
        forceB = force == "Yes"
        await interaction.response.defer(ephemeral=True)
        await self.bot.database.guild_config.update_one(Schemas.GuildConfig(interaction.guild.id), {"$set": {"ephemeral_setting_overpowers_user_setting": forceB}}, upsert=True)

        await interaction.followup.send(f"Guild setting overpowers user setting: {force}", ephemeral=True)

    @ephemeral_messages.command(name='self', description="Configure whether moderation messages are ephemeral or not for yourself")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def ephemeral_messages_user(self, interaction: discord.Interaction, ephemeral: Literal["Yes", "No"]):
        ephemeralB = ephemeral == "Yes"
        await interaction.response.defer(ephemeral=True)
        doc = asyncio.create_task(self.bot.database.guild_config.find_one(Schemas.GuildConfig(interaction.guild.id), Schemas.GuildConfig)) # type: ignore
        await self.bot.database.user_config.update_one(Schemas.UserConfig(interaction.user.id), {"$set": {"ephemeral_moderation_messages": ephemeralB}}, upsert=True)

        doc: Schemas.GuildConfig = await doc # type: ignore
        if doc is not None:
            if doc.ephemeral_setting_overpowers_user_setting:
                await interaction.followup.send(f"Moderation messages are now ephemeral: {ephemeral}\n*(Due to the settings of this guild, all messages are forced to be {"ephemeral" if doc.ephemeral_moderation_messages else "not ephemeral"})*", ephemeral=True)
            else:
                await interaction.followup.send(f"Moderation messages are now ephemeral: {ephemeral}", ephemeral=True)
        else:
            await interaction.followup.send(f"Moderation messages are now ephemeral: {ephemeral}", ephemeral=True)

    @app_commands.command(name='nickname', description="Change nicknames")
    @app_commands.default_permissions(manage_nicknames=True)
    @app_commands.guild_only()
    @app_commands.describe(user="The user to change the nickname of", newnick="The new nickname. Leave blank to reset the nickname")
    async def nickname(self, interaction: discord.Interaction, user: discord.Member, *, newnick: str | None = None):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
            
        # Ensure interaction.user is a Member in guild context
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message('This command requires server member context.', ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=await self.get_ephemeral_messages(interaction.guild, interaction.user))
        if not await self.permissionHierarchyCheck(interaction.user, user):
            await interaction.followup.send(
                "You cannot moderate users higher than you", ephemeral=True)
            return
        try:
            await user.edit(nick=newnick)
        except discord.errors.Forbidden:
            await interaction.followup.send('Missing required permissions. Is the user above me?', ephemeral=True)
        else:
            embed = discord.Embed(
                title=f"Nickname change result", description=None, color=discord.Color.green())
            embed.add_field(name="User", value=user.mention, inline=False)
            embed.add_field(name="Old nickname",
                            value=user.display_name, inline=False)
            embed.add_field(name="New nickname", value=newnick, inline=False)
            embed.set_footer(
                text=f"Moderator: {interaction.user}", icon_url=interaction.user.avatar)
            await interaction.followup.send(embed=embed, ephemeral=await self.get_ephemeral_messages(interaction.guild))

    @app_commands.command(name='purge', description="Purge messages")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def purge(self, interaction: discord.Interaction, limit: int, user: Optional[discord.Member] = None):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=await self.get_ephemeral_messages(interaction.guild))
        msg = []
        if not user:
            if interaction.channel and isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
                await interaction.channel.purge(limit=limit, before=interaction.created_at)
        else:
            if interaction.channel and isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
                async for m in interaction.channel.history():
                    if len(msg) == limit:
                        break
                    if m.author == user:
                        msg.append(m)
                if interaction.channel and hasattr(interaction.channel, 'delete_messages'):
                    await interaction.channel.delete_messages(msg)

        embed = discord.Embed(title=f"Purge result",
                              description=None, color=discord.Color.green())
        embed.add_field(name="Messages purged", value=limit, inline=False)
        embed.set_footer(
            text=f"Moderator: {interaction.user}", icon_url=interaction.user.avatar)
        await interaction.followup.send(embed=embed, ephemeral=await self.get_ephemeral_messages(interaction.guild))

    @app_commands.command(name='mute', description="Mute users")
    @app_commands.default_permissions(mute_members=True)
    @app_commands.guild_only()
    async def mute(self, interaction: discord.Interaction, user: discord.Member, *, reason: Optional[str] = None):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
            
        # Ensure interaction.user is a Member in guild context
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message('This command requires server member context.', ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=await self.get_ephemeral_messages(interaction.guild))
        if not await self.permissionHierarchyCheck(interaction.user, user):
            await interaction.followup.send(
                "You cannot moderate users higher than you", ephemeral=True)
            return

        role = discord.utils.get(interaction.guild.roles, name="Muted")
        if role is None:
            await interaction.followup.send('Muted role not found. Please create a "Muted" role.', ephemeral=True)
            return
            
        await user.add_roles(role, reason=f'by {interaction.user} for {reason}')
        embed = discord.Embed(title=f"Mute result",
                              description=None, color=discord.Color.red())
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Muted", value=user.mention, inline=False)
        embed.set_footer(
            text=f"Moderator: {interaction.user}", icon_url=interaction.user.avatar)
        await interaction.followup.send(embed=embed, ephemeral=await self.get_ephemeral_messages(interaction.guild))

    @app_commands.command(name='unmute', description="Unmute users")
    @app_commands.default_permissions(mute_members=True)
    @app_commands.guild_only()
    async def unmute(self, interaction: discord.Interaction, user: discord.Member):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
            
        # Ensure interaction.user is a Member in guild context
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message('This command requires server member context.', ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=await self.get_ephemeral_messages(interaction.guild))
        if not await self.permissionHierarchyCheck(interaction.user, user):
            await interaction.followup.send(
                "You cannot moderate users higher than you", ephemeral=True)
            return
        # eventually, we will detect mutes from tempmutes
        await user.edit(timed_out_until=None)

        role = discord.utils.get(interaction.guild.roles, name="Muted")
        if role is not None and role in user.roles:
            await user.remove_roles(role)

        embed = discord.Embed(title=f"Unmute result",
                              description=None, color=discord.Color.green())
        embed.add_field(name="Unmuted", value=user.mention, inline=False)
        embed.set_footer(
            text=f"Moderator: {interaction.user}", icon_url=interaction.user.avatar)
        await interaction.followup.send(embed=embed, ephemeral=await self.get_ephemeral_messages(interaction.guild))

    @app_commands.command(name='tempmute', description="Timeout users")
    @app_commands.default_permissions(mute_members=True)
    @app_commands.guild_only()
    async def tempmute(self, interaction: discord.Interaction, user: discord.Member, time: str, *, reason: Optional[str] = None):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
            
        # Ensure interaction.user is a Member in guild context
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message('This command requires server member context.', ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=await self.get_ephemeral_messages(interaction.guild))
        if not await self.permissionHierarchyCheck(interaction.user, user):
            await interaction.followup.send(
                "You cannot moderate users higher than you", ephemeral=True)
            return
        seconds = await self.convert_time_to_seconds(time)
        if seconds is False:
            await interaction.followup.send('Invalid time!', ephemeral=True)
            return
        if seconds > 1209600:
            await interaction.followup.send('Timeouts can only be 2 weeks max!', ephemeral=True)
            return
        until = timedelta(seconds=await self.convert_time_to_seconds(time))
        await user.timeout(until, reason=reason)
        time_formatted = humanize.precisedelta(until, format="%0.0f")
        embed = discord.Embed(title=f"Timeout result",
                              description=None, color=discord.Color.red())
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Timeout", value=user.mention, inline=False)
        embed.add_field(name="Duration", value=time_formatted, inline=False)
        embed.set_footer(
            text=f"Moderator: {interaction.user}", icon_url=interaction.user.avatar)
        await interaction.followup.send(embed=embed, ephemeral=await self.get_ephemeral_messages(interaction.guild))
        await user.send(f"You have been muted in **{interaction.guild}** for *{time_formatted}*")

    @app_commands.command(name='kick', description="Kick users")
    @app_commands.describe(users="The users to kick. Can be multiple users, comma separated.")
    @app_commands.describe(delete_message_time="The time to delete messages from the user. Can be up to 7 days.")
    @app_commands.default_permissions(kick_members=True)
    @app_commands.guild_only()
    async def kick(self, interaction: discord.Interaction, users: str, reason: Optional[str] = None, delete_message_time: Optional[str] = None):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
            
        # Ensure interaction.user is a Member in guild context
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message('This command requires server member context.', ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=await self.get_ephemeral_messages(interaction.guild))
        
        # Parse users list
        user_list = [user.strip() for user in users.split(',')]
        
        # Process delete message time
        max_delete_time = 0
        if delete_message_time is not None:
            try:
                time_seconds = await self.convert_time_to_seconds(delete_message_time)
                if time_seconds is not False:
                    max_delete_time = int(time_seconds)
            except:
                await interaction.followup.send("You cannot input invalid numbers.", ephemeral=True)
                return

        converter: commands.MemberConverter = commands.MemberConverter()
        ctx = await commands.Context.from_interaction(interaction)
        kicked_users: list[discord.Member] = []
        
        for user_str in user_list:
            try:
                user = await converter.convert(ctx, user_str)
                if not await self.permissionHierarchyCheck(interaction.user, user):
                    await interaction.followup.send(
                        "You cannot moderate users higher than you", ephemeral=True)
                    return

                await interaction.guild.kick(user, reason=reason)
                kicked_users.append(user)
            except Exception as e:
                await interaction.followup.send(f"Failed to kick user {user_str}: {str(e)}", ephemeral=True)
                return

        # Delete messages if specified
        if max_delete_time > 0:
            for channel in interaction.guild.channels:
                if isinstance(channel, (discord.TextChannel, discord.Thread)):
                    try:
                        async for message in channel.history():
                            if message.author in kicked_users:
                                if message.created_at > interaction.created_at - timedelta(seconds=max_delete_time):
                                    await message.delete()
                    except Exception:
                        pass  # Ignore permission errors for channels

        embed = discord.Embed(title=f"Kick result", description=None, color=discord.Color.red())
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Kicked", value=', '.join([user.mention for user in kicked_users]), inline=False)
        embed.set_footer(text=f"Moderator: {interaction.user}", icon_url=interaction.user.avatar)
        await interaction.followup.send(embed=embed, ephemeral=await self.get_ephemeral_messages(interaction.guild))

    @app_commands.command(name='ban', description="Ban users")
    @app_commands.describe(users="The users to ban. Can be multiple users, comma separated.")
    @app_commands.describe(delete_message_time="The time to delete messages from the user. Can be up to 7 days.")
    @app_commands.default_permissions(ban_members=True)
    @app_commands.guild_only()
    async def ban(self, interaction: discord.Interaction, users: str, reason: Optional[str] = None, delete_message_time: Optional[str] = None):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
            
        # Ensure interaction.user is a Member in guild context
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message('This command requires server member context.', ephemeral=True)
            return

        await interaction.response.defer(ephemeral=await self.get_ephemeral_messages(interaction.guild))

        # Process delete message time
        delete_message_seconds = 0
        if delete_message_time is not None:
            try:
                time_result = await self.convert_time_to_seconds(delete_message_time)
                if time_result is not False:
                    delete_message_seconds = int(time_result)
            except:
                await interaction.followup.send("You cannot input invalid numbers.", ephemeral=True)
                return
        
        if delete_message_seconds > 604800:
            await interaction.followup.send("You can only delete messages up to 7 days old", ephemeral=True)
            return
        
        # Parse users list
        user_list = [user.strip() for user in users.split(',')]

        converter: commands.MemberConverter = commands.MemberConverter()
        ctx = await commands.Context.from_interaction(interaction)
        banned_users: list[discord.Member] = []
        
        for user_str in user_list:
            try:
                user = await converter.convert(ctx, user_str)
                if not await self.permissionHierarchyCheck(interaction.user, user):
                    await interaction.followup.send(
                        "You cannot moderate users higher than you", ephemeral=True)
                    return

                await interaction.guild.ban(user, reason=reason, delete_message_seconds=delete_message_seconds)
                banned_users.append(user)
            except Exception as e:
                await interaction.followup.send(f"Failed to ban user {user_str}: {str(e)}", ephemeral=True)
                return

        embed = discord.Embed(title=f"Ban result", description=None, color=discord.Color.red())
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Banned", value=', '.join([user.mention for user in banned_users]), inline=False)
        embed.set_footer(text=f"Moderator: {interaction.user}", icon_url=interaction.user.avatar)
        await interaction.followup.send(embed=embed, ephemeral=await self.get_ephemeral_messages(interaction.guild))

    @app_commands.command(name='unban', description="Unban users")
    @app_commands.describe(users="The users to unban. Can be multiple users, comma separated.")
    @app_commands.default_permissions(ban_members=True)
    @app_commands.guild_only()
    async def unban(self, interaction: discord.Interaction, users: str, reason: Optional[str] = None):
        assert interaction.guild is not None

        await interaction.response.defer(ephemeral=await self.get_ephemeral_messages(interaction.guild))
        users_list = [user.strip() for user in users.split(',')]

        converter: commands.MemberConverter = commands.MemberConverter()
        ctx = await commands.Context.from_interaction(interaction)
        discord_users: list[discord.Member] = []
        for _, _user in enumerate(users_list):
            try:
                user = await converter.convert(ctx, _user)
                discord_users.append(user)
            except:
                await interaction.followup.send(
                    f"User {_user} not found", ephemeral=True)
                return

            await interaction.guild.unban(user, reason=reason)

        embed = discord.Embed(title=f"Unban result",
                              description=None, color=discord.Color.red())
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Unbanned", value=', '.join(
            [user.mention for user in discord_users]), inline=False)
        embed.set_footer(
            text=f"Moderator: {interaction.user}", icon_url=interaction.user.avatar)
        await interaction.followup.send(embed=embed, ephemeral=await self.get_ephemeral_messages(interaction.guild))

    @app_commands.command(name='warn', description="Warn users")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def warn(self, interaction: discord.Interaction, user: discord.Member, *, reason: str):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
            
        # Ensure interaction.user is a Member in guild context
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message('This command requires server member context.', ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=await self.get_ephemeral_messages(interaction.guild))
        if not await self.permissionHierarchyCheck(interaction.user, user):
            await interaction.followup.send(
                "You cannot moderate users higher than you", ephemeral=True)
            return
        
        doc = await self.bot.database.warnings.find_one(
            Schemas.WarnSchema(user.id, interaction.guild.id), Schemas.WarnSchema)
        if doc is None:
            doc = Schemas.WarnSchema(user.id, interaction.guild.id)
            # Handle both dict and schema access patterns
            if hasattr(doc, 'warns'):
                doc.warns = []
            elif isinstance(doc, dict):
                doc['warns'] = []
        
        warn_dict = {
            "reason": reason,
            "timestamp": int(interaction.created_at.timestamp()),
            "moderator": interaction.user.id,
            "id": str(uuid4())
        }
        
        # Safe access for both dict and schema
        if isinstance(doc, dict):
            warns_list = doc.get('warns', [])
            warns_list.append(warn_dict)
            doc['warns'] = warns_list
            doc_dict = doc
        else:
            warns_list = getattr(doc, 'warns', [])
            if warns_list is None:
                warns_list = []
            warns_list.append(warn_dict)
            # For schema objects, create a new dict with updated warns
            doc_dict = doc.to_dict() if hasattr(doc, 'to_dict') else {}
            doc_dict['warns'] = warns_list
        await self.bot.database.warnings.update_one(Schemas.WarnSchema(user.id, interaction.guild.id), {"$set": doc_dict}, upsert=True)
        
        dm_embed = discord.Embed(title=f"You have been warned in {interaction.guild}", color=discord.Color.red())
        dm_embed.add_field(name="Reason", value=reason, inline=False)
        dm_embed.add_field(name="Warn ID", value=warn_dict['id'], inline=False)
        dm_embed.set_footer(text=f"This is your {ordinal(len(warns_list))} warn")

        failed_dms = False
        try:
            await user.send(embed=dm_embed)
        except discord.errors.Forbidden:
            failed_dms = True

        embed = discord.Embed(title=f"Warn result", description=None, color=discord.Color.red())
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Warned", value=user.mention, inline=False)
        embed.add_field(name="Moderator", value=f"{interaction.user.mention}\n\nThis is their {ordinal(len(warns_list))} warn", inline=False)
        if failed_dms:
            embed.add_field(name="Failed to DM user", value="User has DMs disabled", inline=False)
        embed.set_footer(text=f"Warn ID: {warn_dict['id']}")
        await interaction.followup.send(embed=embed, ephemeral=await self.get_ephemeral_messages(interaction.guild))

    @app_commands.command(name='warns', description="Get warnings for a user")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def warnings(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer()
        view = WarningsView(self.bot, user)
        await view.async_init()
        embed = discord.Embed(title=f"Warnings for {user}", color=discord.Color.red())
        await interaction.followup.send(embed=embed, view=view)
        view.message = await interaction.original_response()
        await view.update()

    @app_commands.command(name='warninfo', description="Get information about a warning")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def warninfo(self, interaction: discord.Interaction, warn_id: str):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=await self.get_ephemeral_messages(interaction.guild))
        
        # Find the warning by ID
        raw_doc = await self.bot.database.database.warnings.find_one({"warns.id": warn_id})
        if raw_doc is None:
            await interaction.followup.send("Warn not found", ephemeral=True)
            return
            
        doc = Schemas.WarnSchema.from_dict(raw_doc) if raw_doc else None
        if doc is None:
            await interaction.followup.send("This user has no warnings", ephemeral=True)
            return

        # Safe access for warns
        warns_list = doc.get('warns') if isinstance(doc, dict) else getattr(doc, 'warns', [])
        if warns_list is None:
            warns_list = []
            
        warn_found = None
        for warn in warns_list:
            if warn['id'] == warn_id:
                warn_found = warn
                break
                
        if warn_found is None:
            await interaction.followup.send("Warn not found", ephemeral=True)
            return

        # Safe access for user_id
        user_id = doc.get('user_id') if isinstance(doc, dict) else getattr(doc, 'user_id', None)
        if user_id is None:
            await interaction.followup.send("User ID not found", ephemeral=True)
            return
            
        user = await self.bot.fetch_user(user_id)

        embed = discord.Embed(title=f"Warn information", color=discord.Color.red())
        embed.add_field(name="Reason", value=warn_found['reason'], inline=False)
        embed.add_field(name="User", value=user.mention, inline=False)
        embed.add_field(name="Moderator", value=(await self.bot.fetch_user(warn_found['moderator'])).mention, inline=False)
        embed.add_field(name="Timestamp", value=f"<t:{warn_found['timestamp']}>", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=await self.get_ephemeral_messages(interaction.guild))

    @app_commands.command(name='clearwarns', description="Clear all warnings for a user")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def clearwarns(self, interaction: discord.Interaction, user: discord.Member):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
            
        # Ensure interaction.user is a Member in guild context
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message('This command requires server member context.', ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=await self.get_ephemeral_messages(interaction.guild))
        if not await self.permissionHierarchyCheck(interaction.user, user):
            await interaction.followup.send(
                "You cannot moderate users higher than you", ephemeral=True)
            return

        await self.bot.database.warnings.delete_one(Schemas.WarnSchema(user.id, interaction.guild.id))
        await interaction.followup.send("Warnings cleared", ephemeral=await self.get_ephemeral_messages(interaction.guild))

    @app_commands.command(name='unwarn', description="Delete a warning")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def delwarn(self, interaction: discord.Interaction, user: discord.Member, warn_id: str):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
            
        # Ensure interaction.user is a Member in guild context
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message('This command requires server member context.', ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=await self.get_ephemeral_messages(interaction.guild))
        if not await self.permissionHierarchyCheck(interaction.user, user):
            await interaction.followup.send(
                "You cannot moderate users higher than you", ephemeral=True)
            return

        doc = await self.bot.database.warnings.find_one(Schemas.WarnSchema(user.id, interaction.guild.id), Schemas.WarnSchema)
        if doc is None:
            await interaction.followup.send("This user has no warnings", ephemeral=True)
            return

        # Safe access for both dict and schema
        warns_list = doc.get('warns') if isinstance(doc, dict) else getattr(doc, 'warns', [])
        if warns_list is None:
            warns_list = []

        warn_found = False
        for i, warn in enumerate(warns_list):
            if warn['id'] == warn_id:
                del warns_list[i]
                warn_found = True
                break
                
        if not warn_found:
            await interaction.followup.send("Warn not found", ephemeral=True)
            return

        # Update the document with modified warns list
        if isinstance(doc, dict):
            doc['warns'] = warns_list
            doc_dict = doc
        else:
            # For schema objects, create a new dict with updated warns
            doc_dict = doc.to_dict() if hasattr(doc, 'to_dict') else {}
            doc_dict['warns'] = warns_list

        await self.bot.database.warnings.update_one(Schemas.WarnSchema(user.id, interaction.guild.id), {"$set": doc_dict}, upsert=True)

        await interaction.followup.send("Warn deleted", ephemeral=await self.get_ephemeral_messages(interaction.guild))


async def setup(bot):
    await bot.add_cog(Moderation(bot))
