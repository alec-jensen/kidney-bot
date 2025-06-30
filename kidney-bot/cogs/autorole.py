import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from typing import Literal

from utils.kidney_bot import KidneyBot
from utils.views import Confirm


class Autorole(commands.Cog):
    def __init__(self, bot):
        self.bot: KidneyBot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info('Autorole cog loaded.')

        await self.bot.wait_until_ready()
        self.autorole_loop.start()

    @tasks.loop(seconds=60)
    async def autorole_loop(self):
        for guild in self.bot.guilds:
            doc: dict = await self.bot.database.autorolesettings.find_one({'guild': guild.id}) # type: ignore
            if doc is None:
                continue
            for role in doc.get('roles', []):
                discord_role = guild.get_role(role['id'])

                if discord_role is None:
                    continue

                for member in guild.members:
                    if discord_role in member.roles:
                        continue

                    if member.bot and not doc.get('BotsGetRoles', False):
                        continue
                    
                    if member.joined_at is None:
                        continue

                    if (member.joined_at.timestamp() + role['delay']) <= discord.utils.utcnow().timestamp():
                        await member.add_roles(discord_role)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        doc: dict = await self.bot.database.autorolesettings.find_one({'guild': member.guild.id}) # type: ignore
        if doc is None:
            return

        invalid_role_ids: list[int] = []

        for role in doc.get('roles', []):
            discord_role = member.guild.get_role(role['id'])

            if discord_role is None:
                invalid_role_ids.append(role['id'])
                continue

            if role.get('delay') > 0:
                continue

            if member.bot and not doc.get('BotsGetRoles', False):
                continue

            await member.add_roles(discord_role)

        # Remove invalid roles from the database
        if len(invalid_role_ids) > 0:
            doc['roles'] = [role for role in doc['roles'] if role['id'] not in invalid_role_ids]
            await self.bot.database.autorolesettings.update_one({'guild': member.guild.id}, {'$set': {'roles': doc['roles']}})

    autorole: app_commands.Group = app_commands.Group(name='autorole', description='Manage autorole settings',
                                                      default_permissions=discord.Permissions(manage_guild=True))

    @autorole.command(name='add', description='Add a role to the autorole list.')
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(role='The role to add to the autorole list.', delay='The delay in seconds before the role is given to the user.')
    @app_commands.guild_only()
    async def add(self, interaction: discord.Interaction, role: discord.Role, delay: int = 0):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        if role.position >= interaction.guild.me.top_role.position:
            await interaction.followup.send(f'Cannot add {role.mention} to the autorole list, it is higher than my top role.', ephemeral=True)
            return
        
        def _role_is_moderator(role: discord.Role) -> bool:
            return role.permissions.administrator or role.permissions.manage_guild or role.permissions.manage_channels \
                or role.permissions.manage_roles or role.permissions.manage_messages or role.permissions.ban_members or \
                    role.permissions.kick_members or role.permissions.manage_nicknames or role.permissions.manage_webhooks
        
        if _role_is_moderator(role):
            view = Confirm(accept_response=f'Added {role.mention} to the autorole list.', deny_response='Cancelled', ephemeral=True)

            await interaction.followup.send(
                f'It appears the role {role.mention} has moderation permissions.\n**If you add this role, EVERY MEMBER OF THIS SERVER WILL RECIEVE IT**',
                ephemeral=True, view=view)
            
            await view.wait()
            if view.value is None or not view.value:
                return
        
        doc = await self.bot.database.autorolesettings.find_one({'guild': interaction.guild.id})
        if doc is None:
            await self.bot.database.autorolesettings.insert_one({'guild': interaction.guild.id, 'roles': [{'id': role.id, 'delay': delay}]})
        else:
            # Safe access for both dict and schema
            roles_list = doc.get('roles', []) if isinstance(doc, dict) else getattr(doc, 'roles', [])
            for role_dict in roles_list:
                if role_dict['id'] == role.id:
                    await interaction.followup.send(f'{role} is already in the autorole list.', ephemeral=True)
                    return
                
            roles_list.append({'id': role.id, 'delay': delay})
            await self.bot.database.autorolesettings.update_one({'guild': interaction.guild.id}, {'$set': {'roles': roles_list}})

        # Clean up invalid roles
        doc = await self.bot.database.autorolesettings.find_one({'guild': interaction.guild.id})
        if doc is not None:
            # Safe access for both dict and schema
            roles_list = doc.get('roles', []) if isinstance(doc, dict) else getattr(doc, 'roles', [])
            valid_roles = []
            for role_data in roles_list:
                discord_role = interaction.guild.get_role(role_data['id'])
                if discord_role is not None:
                    valid_roles.append(role_data)

            await self.bot.database.autorolesettings.update_one({'guild': interaction.guild.id}, {'$set': {'roles': valid_roles}})

        if not _role_is_moderator(role):
            await interaction.followup.send(f'Added {role.mention} to the autorole list.', ephemeral=True)

    @autorole.command(name='remove', description='Remove a role from the autorole list.')
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(role='The role to remove from the autorole list.')
    @app_commands.guild_only()
    async def remove(self, interaction: discord.Interaction, role: discord.Role):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        doc = await self.bot.database.autorolesettings.find_one({'guild': interaction.guild.id})
        if doc is None:
            await interaction.followup.send(f'No roles are set for autorole.', ephemeral=True)
            return
            
        # Safe access for both dict and schema
        roles_list = doc.get('roles', []) if isinstance(doc, dict) else getattr(doc, 'roles', [])
        roles_list = [role_dict for role_dict in roles_list if role_dict['id'] != role.id]
        
        await self.bot.database.autorolesettings.update_one({'guild': interaction.guild.id}, {'$set': {'roles': roles_list}})
        await interaction.followup.send(f'Removed {role} from the autorole list.', ephemeral=True)

        # Clean up invalid roles
        doc = await self.bot.database.autorolesettings.find_one({'guild': interaction.guild.id})
        if doc is not None:
            # Safe access for both dict and schema
            roles_list = doc.get('roles', []) if isinstance(doc, dict) else getattr(doc, 'roles', [])
            valid_roles = []
            for role_data in roles_list:
                discord_role = interaction.guild.get_role(role_data['id'])
                if discord_role is not None:
                    valid_roles.append(role_data)

            await self.bot.database.autorolesettings.update_one({'guild': interaction.guild.id}, {'$set': {'roles': valid_roles}})

    @autorole.command(name='delay', description='Set the delay for a role in the autorole list.')
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(role='The role to set the delay for.', delay='The delay in seconds before the role is given to the user.')
    @app_commands.describe(delay='The delay in seconds before the role is given to the user.')
    @app_commands.guild_only()
    async def delay(self, interaction: discord.Interaction, role: discord.Role, delay: int):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        doc = await self.bot.database.autorolesettings.find_one({'guild': interaction.guild.id})
        if doc is None:
            await interaction.followup.send(f'No roles are set for autorole.', ephemeral=True)
            return
            
        # Safe access for both dict and schema
        roles_list = doc.get('roles', []) if isinstance(doc, dict) else getattr(doc, 'roles', [])
        for role_dict in roles_list:
            if role_dict['id'] == role.id:
                role_dict['delay'] = delay
                break
                
        await self.bot.database.autorolesettings.update_one({'guild': interaction.guild.id}, {'$set': {'roles': roles_list}})
        await interaction.followup.send(f'Set the delay for {role} to {delay} seconds.', ephemeral=True)

        # Clean up invalid roles
        doc = await self.bot.database.autorolesettings.find_one({'guild': interaction.guild.id})
        if doc is not None:
            # Safe access for both dict and schema
            roles_list = doc.get('roles', []) if isinstance(doc, dict) else getattr(doc, 'roles', [])
            valid_roles = []
            for role_data in roles_list:
                discord_role = interaction.guild.get_role(role_data['id'])
                if discord_role is not None:
                    valid_roles.append(role_data)

            await self.bot.database.autorolesettings.update_one({'guild': interaction.guild.id}, {'$set': {'roles': valid_roles}})

    @autorole.command(name='list', description='List all roles in the autorole list.')
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def list(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        doc = await self.bot.database.autorolesettings.find_one({'guild': interaction.guild.id})
        if doc is None:
            await interaction.followup.send(f'No roles are set for autorole.', ephemeral=True)
            return

        # Safe access for both dict and schema
        roles_list = doc.get('roles', []) if isinstance(doc, dict) else getattr(doc, 'roles', [])
        role_names: list[str] = []
        for role_dict in roles_list:
            role_obj = interaction.guild.get_role(role_dict['id'])
            if role_obj is None:
                continue
            role_names.append(
                f'{role_obj.mention}' + (f' (delay: {role_dict["delay"]} seconds)' if role_dict['delay'] > 0 else ''))

        await interaction.followup.send('\n'.join(role_names), ephemeral=True)

        # Clean up invalid roles
        doc = await self.bot.database.autorolesettings.find_one({'guild': interaction.guild.id})
        if doc is not None:
            # Safe access for both dict and schema
            roles_list = doc.get('roles', []) if isinstance(doc, dict) else getattr(doc, 'roles', [])
            valid_roles = []
            for role_data in roles_list:
                discord_role = interaction.guild.get_role(role_data['id'])
                if discord_role is not None:
                    valid_roles.append(role_data)

            await self.bot.database.autorolesettings.update_one({'guild': interaction.guild.id}, {'$set': {'roles': valid_roles}})

    @autorole.command(name='settings', description='Set miscellaneous settings for autorole.')
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def settings(self, interaction: discord.Interaction, option: Literal["BotsGetRoles"], value: bool):
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        doc = await self.bot.database.autorolesettings.find_one({'guild': interaction.guild.id})
        if doc is None:
            await interaction.followup.send(f'No roles are set for autorole.', ephemeral=True)
            return
        
        # Update the specific setting
        await self.bot.database.autorolesettings.update_one({'guild': interaction.guild.id}, {'$set': {option: value}})
        await interaction.followup.send(f'Set {option} to {value}.', ephemeral=True)

        # Clean up invalid roles
        doc = await self.bot.database.autorolesettings.find_one({'guild': interaction.guild.id})
        if doc is not None:
            # Safe access for both dict and schema
            roles_list = doc.get('roles', []) if isinstance(doc, dict) else getattr(doc, 'roles', [])
            valid_roles = []
            for role_data in roles_list:
                discord_role = interaction.guild.get_role(role_data['id'])
                if discord_role is not None:
                    valid_roles.append(role_data)

            await self.bot.database.autorolesettings.update_one({'guild': interaction.guild.id}, {'$set': {'roles': valid_roles}})


async def setup(bot):
    await bot.add_cog(Autorole(bot))
