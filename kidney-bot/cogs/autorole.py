import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from typing import Literal

from utils.kidney_bot import KidneyBot

class Autorole(commands.Cog):
    def __init__(self, bot):
        self.bot: KidneyBot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info('Autorole cog loaded.')
        self.autorole_loop.start()

    @tasks.loop(seconds=1)
    async def autorole_loop(self):
        for guild in self.bot.guilds:
            doc: dict = await self.bot.database.autorole_settings.find_one({'guild': guild.id})
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
                    
                    if (member.joined_at.timestamp() + role['delay']) <= discord.utils.utcnow().timestamp():
                        await member.add_roles(discord_role)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        doc: dict = await self.bot.database.autorole_settings.find_one({'guild': member.guild.id})
        if doc is None:
            return
        
        invalid_roles: list[discord.Role] = []

        for role in doc.get('roles', []):
            discord_role = member.guild.get_role(role['id'])

            if discord_role is None:
                invalid_roles.append(discord_role)
                continue

            if role.get('delay') > 0:
                continue

            if member.bot and not doc.get('BotsGetRoles', False):
                continue

            await member.add_roles(discord_role)
        
        # Remove invalid roles from the database
        if len(invalid_roles) > 0:
            doc['roles'] = [role for role in doc['roles'] if role['id'] not in [role.id for role in invalid_roles]]
            await self.bot.database.autorole_settings.update_one({'guild': member.guild.id}, {'$set': {'roles': doc['roles']}})

    autorole: app_commands.Group = app_commands.Group(name='autorole', description='Manage autorole settings',
                                        default_permissions=discord.Permissions(manage_guild=True))
    
    @autorole.command(name='add', description='Add a role to the autorole list.')
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(role='The role to add to the autorole list.', delay='The delay in seconds before the role is given to the user.')
    async def add(self, interaction: discord.Interaction, role: discord.Role, delay: int = 0):
        doc = await self.bot.database.autorole_settings.find_one({'guild': interaction.guild.id})
        if doc is None:
            await self.bot.database.autorole_settings.insert_one({'guild': interaction.guild.id, 'roles': [{'id': role.id, 'delay': 0}]})
        else:
            doc['roles'].append({'id': role.id, 'delay': delay})
            await self.bot.database.autorole_settings.update_one({'guild': interaction.guild.id}, {'$set': {'roles': doc['roles']}})
        await interaction.response.send_message(f'Added {role} to the autorole list.', ephemeral=True)

        for role in doc.get('roles', []):
            discord_role = interaction.guild.get_role(role['id'])
            if discord_role is None:
                doc['roles'].remove(role)

        await self.bot.database.autorole_settings.update_one({'guild': interaction.guild.id}, {'$set': {'roles': doc['roles']}})

    @autorole.command(name='remove', description='Remove a role from the autorole list.')
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(role='The role to remove from the autorole list.')
    async def remove(self, interaction: discord.Interaction, role: discord.Role):
        doc = await self.bot.database.autorole_settings.find_one({'guild': interaction.guild.id})
        if doc is None:
            await interaction.response.send_message(f'No roles are set for autorole.', ephemeral=True)
            return
        doc['roles'] = [role_dict for role_dict in doc['roles'] if role_dict['id'] != role.id]
        await self.bot.database.autorole_settings.update_one({'guild': interaction.guild.id}, {'$set': {'roles': doc['roles']}})
        await interaction.response.send_message(f'Removed {role} from the autorole list.', ephemeral=True)

        for role in doc.get('roles', []):
            discord_role = interaction.guild.get_role(role['id'])
            if discord_role is None:
                doc['roles'].remove(role)

        await self.bot.database.autorole_settings.update_one({'guild': interaction.guild.id}, {'$set': {'roles': doc['roles']}})

    @autorole.command(name='delay', description='Set the delay for a role in the autorole list.')
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(role='The role to set the delay for.', delay='The delay in seconds before the role is given to the user.')
    @app_commands.describe(delay='The delay in seconds before the role is given to the user.')
    async def delay(self, interaction: discord.Interaction, role: discord.Role, delay: int):
        doc = await self.bot.database.autorole_settings.find_one({'guild': interaction.guild.id})
        if doc is None:
            await interaction.response.send_message(f'No roles are set for autorole.', ephemeral=True)
            return
        for role_dict in doc['roles']:
            if role_dict['id'] == role.id:
                role_dict['delay'] = delay
                break
        await self.bot.database.autorole_settings.update_one({'guild': interaction.guild.id}, {'$set': {'roles': doc['roles']}})
        await interaction.response.send_message(f'Set the delay for {role} to {delay} seconds.', ephemeral=True)

        for role in doc.get('roles', []):
            discord_role = interaction.guild.get_role(role['id'])
            if discord_role is None:
                doc['roles'].remove(role)
        
        await self.bot.database.autorole_settings.update_one({'guild': interaction.guild.id}, {'$set': {'roles': doc['roles']}})
    
    @autorole.command(name='list', description='List all roles in the autorole list.')
    @app_commands.default_permissions(manage_guild=True)
    async def list(self, interaction: discord.Interaction):
        doc = await self.bot.database.autorole_settings.find_one({'guild': interaction.guild.id})
        if doc is None:
            await interaction.response.send_message(f'No roles are set for autorole.', ephemeral=True)
            return
        
        role_names: list[str] = []
        for role_dict in doc['roles']:
            role = interaction.guild.get_role(role_dict['id'])
            if role is None:
                continue
            role_names.append(f'{role.mention}' + (f' (delay: {role_dict["delay"]} seconds)' if role_dict['delay'] > 0 else ''))
        
        await interaction.response.send_message('\n'.join(role_names), ephemeral=True)

        for role in doc.get('roles', []):
            discord_role = interaction.guild.get_role(role['id'])
            if discord_role is None:
                doc['roles'].remove(role)
        
        await self.bot.database.autorole_settings.update_one({'guild': interaction.guild.id}, {'$set': {'roles': doc['roles']}})

    @autorole.command(name='settings', description='Set miscellaneous settings for autorole.')
    @app_commands.default_permissions(manage_guild=True)
    async def settings(self, interaction: discord.Interaction, option: Literal["BotsGetRoles"], value: bool):
        doc = await self.bot.database.autorole_settings.find_one({'guild': interaction.guild.id})
        if doc is None:
            await interaction.response.send_message(f'No roles are set for autorole.', ephemeral=True)
            return
        doc[option] = value
        await self.bot.database.autorole_settings.update_one({'guild': interaction.guild.id}, {'$set': doc})
        await interaction.response.send_message(f'Set {option} to {value}.', ephemeral=True)

        for role in doc.get('roles', []):
            discord_role = interaction.guild.get_role(role['id'])
            if discord_role is None:
                doc['roles'].remove(role)
        
        await self.bot.database.autorole_settings.update_one({'guild': interaction.guild.id}, {'$set': {'roles': doc['roles']}})


async def setup(bot):
    await bot.add_cog(Autorole(bot))
