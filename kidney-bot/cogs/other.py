# This cog creates all uncategorized commands
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import logging
from typing import Literal

import discord
import psutil
from discord import app_commands
from discord.ext import commands

from utils import checks
from utils.database import Schemas
from utils.kidney_bot import KidneyBot
from utils.views import Confirm


def check_user(user: discord.User | discord.Member):
    async def predicate(interaction: discord.Interaction):
        return interaction.user == user
    return predicate


class SetupView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.value = None

    @discord.ui.button(label='Set up Auto Role', style=discord.ButtonStyle.blurple)
    async def auto_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot: KidneyBot = interaction.client  # type: ignore
        embed = discord.Embed(title='Auto Role', color=discord.Color.blue())
        embed.add_field(
            name='Auto Role', value='Auto Role is a feature that automatically gives roles to users when they join.')
        embed.add_field(name='Enable Auto Role',
                        value='Would you like to enable Auto Role?')

        view = discord.ui.View()
        roleSelect = discord.ui.RoleSelect(placeholder='Please select the roles you would like to be automatically given to new members.', min_values=1, max_values=25)

        async def callback(interaction: discord.Interaction):
            view.interaction = interaction  # type: ignore
            view.stop()

        roleSelect.callback = callback
        view.add_item(roleSelect)
        view.interaction_check = check_user(interaction.user)
        await interaction.response.send_message(embed=embed, view=view)
        await view.wait()

        if not hasattr(view.children[0], 'values') or len(view.children[0].values) == 0:  # type: ignore
            return

        roles = [{'id': role.id, 'delay': 0} for role in view.children[0].values]  # type: ignore

        msg = "Would you like bots to get roles?"
        view2 = Confirm(accept_response='Bots will get roles.', deny_response='Bots will not get roles.')
        view2.interaction_check = check_user(interaction.user)
        if hasattr(view, 'interaction') and view.interaction is not None:  # type: ignore
            await view.interaction.response.send_message(msg, view=view2)  # type: ignore
        else:
            if interaction.channel and hasattr(interaction.channel, 'send'):
                await interaction.channel.send(msg, view=view2)  # type: ignore

        await view2.wait()

        if interaction.guild:
            doc = await bot.database.autorolesettings.get(interaction.guild.id) or \
                  Schemas.AutoRoleSettings(guild_id=interaction.guild.id)
            doc.roles = roles
            doc.bots_get_roles = view2.value
            await bot.database.autorolesettings.save(doc)

    @discord.ui.button(label='Set up Moderation', style=discord.ButtonStyle.blurple)
    async def moderation(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot: KidneyBot = interaction.client  # type: ignore
        embed = discord.Embed(title='Moderation', color=discord.Color.blue())
        embed.add_field(name="Ephemeral Messages", value="Would you like to enable ephemeral messages for moderation command outputs?")
        view = Confirm(accept_response='Ephemeral messages enabled.', deny_response='Ephemeral messages will not be enabled.')
        view.interaction_check = check_user(interaction.user)
        await interaction.response.send_message(embed=embed, view=view)
        await view.wait()
        if interaction.guild and view.value is not None:
            cfg = await bot.database.guild_config.get(interaction.guild.id) or \
                  Schemas.GuildConfig(guild_id=interaction.guild.id)
            cfg.ephemeral_moderation_messages = bool(view.value)
            await bot.database.guild_config.save(cfg)

        embed = discord.Embed(title='Force Guild Ephemeral Setting', color=discord.Color.blue())
        embed.add_field(name="Force Guild Ephemeral Setting", value="Would you like to force all moderation command outputs to use the guild's ephemeral setting?")
        view = Confirm(accept_response='Force guild ephemeral setting enabled.', deny_response='Force guild ephemeral setting will not be enabled.')
        view.interaction_check = check_user(interaction.user)
        if interaction.channel and hasattr(interaction.channel, 'send'):
            await interaction.channel.send(embed=embed, view=view)  # type: ignore
        await view.wait()
        if interaction.guild and view.value is not None:
            cfg = await bot.database.guild_config.get(interaction.guild.id) or \
                  Schemas.GuildConfig(guild_id=interaction.guild.id)
            cfg.ephemeral_setting_overpowers_user_setting = bool(view.value)
            await bot.database.guild_config.save(cfg)


class Other(commands.Cog):

    def __init__(self, bot: KidneyBot):
        self.bot: KidneyBot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info('Other cog loaded.')

    @app_commands.command(name='invite', description='Invite the bot to your own server')
    async def invite(self, interaction: discord.Interaction):
        await interaction.response.send_message("Invite the bot here! https://discord.com/api/oauth2/authorize?client_id=870379086487363605&permissions=8&scope=bot")

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
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        embed = discord.Embed(title='Guild Settings Overview', color=discord.Color.blue())

        ams = await self.bot.database.automodsettings.get(interaction.guild.id)
        if ams is not None:
            whitelist = []
            for uid in (ams.whitelist or []):
                m = interaction.guild.get_member(uid)
                c = interaction.guild.get_channel(uid)
                whitelist.append(m.mention if m else (c.mention if c else str(uid)))
            log_channel = interaction.guild.get_channel(ams.log_channel) if ams.log_channel else None
            embed.add_field(name='Auto Mod', value=f'Log Channel: {log_channel.mention if log_channel else None}\nWhitelist: {", ".join(whitelist)}')

        ars = await self.bot.database.autorolesettings.get(interaction.guild.id)
        if ars is not None:
            roles = []
            for role_data in (ars.roles or []):
                _role = interaction.guild.get_role(role_data['id'])
                if _role:
                    _str = _role.mention
                    delay = role_data.get('delay', 0)
                    if delay and int(delay) > 0:
                        _str += f' (Delay: {delay})'
                    roles.append(_str)
            embed.add_field(name='Auto Role', value=f'Roles: {", ".join(roles)}\nBots get roles: {ars.bots_get_roles}')

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name='setup', description='Setup the bot for your server.')
    @app_commands.guild_only()
    async def setup(self, interaction: discord.Interaction):
        embed = discord.Embed(title='Setup', color=discord.Color.blue())
        embed.add_field(
            name='Active Guard', value='Active Guard is a feature that blocks known bot accounts from joining your server.')
        embed.add_field(
            name='AI Detection', value='AI Detection is a feature that detects toxicity in messages and takes action if the toxicity is above a certain threshold.')
        embed.add_field(name='Permission Timeout',
                        value='Permission Timeout is a feature that ensures users have been a member of your server for a certain amount of time before they can use moderation permissions.')
        embed.add_field(
            name='Auto Role', value='Auto Role is a feature that automatically gives roles to users when they join.')
        embed.add_field(
            name='Moderation', value='kidney bot has a variety of moderation commands with lots of customization options')

        view = SetupView()
        await interaction.response.send_message(embed=embed, view=view)

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

        doc = await self.bot.database.user_config.get(interaction.user.id) or \
              Schemas.UserConfig(user_id=interaction.user.id)
        doc.announce_level = announce_level
        await self.bot.database.user_config.save(doc)
        await interaction.response.send_message(f'Announce level set to {level}', ephemeral=True)

    @commands.command()
    @checks.is_bot_owner()
    async def announce(self, ctx: commands.Context, level: str, *, message: str):
        """Send a global message to all server owners."""

        level = level.title()

        if level not in self.announce_levels.values() and not (level.isdigit() and int(level) in self.announce_levels):
            await ctx.reply(self.bot.get_lang_string('other.announce.invalid_level'))
            return

        if level.isdigit():
            announce_level = int(level)
        else:
            announce_level = {v: k for k,
                              v in self.announce_levels.items()}.get(level)

        if announce_level is None:
            await ctx.reply(self.bot.get_lang_string('other.announce.invalid_level'))
            return

        await ctx.reply(f'Sending global message\n```{message}```')
        ids = []

        users: list[discord.User | discord.Member] = []

        for guild in self.bot.guilds:
            if guild.owner_id not in ids and guild.owner is not None:
                users.append(guild.owner)
                ids.append(guild.owner_id)

        user_configs = await self.bot.database.user_config.query_many({'announce_level': {'$gte': announce_level}})

        for user_cfg in user_configs:
            if user_cfg.user_id and int(user_cfg.user_id) not in ids:
                users.append(await self.bot.fetch_user(user_cfg.user_id))
                ids.append(int(user_cfg.user_id))

        ids = []

        successfully_sent = 0
        not_sent = 0
        error = 0

        for user in users:
            if int(user.id) not in ids:
                user_config = await self.bot.database.user_config.get(user.id)

                if user_config is None:
                    user_config = Schemas.UserConfig(
                        user_id=user.id, announce_level=1)

                if user_config.announce_level is None:
                    user_config.announce_level = 1

                if user_config.announce_level == 0:
                    not_sent += 1
                    continue

                if user_config.announce_level < announce_level:
                    not_sent += 1
                    continue

                try:
                    await user.send(
                        f'Message from the dev!\n{message}\n\n(you are receiving this, because you either own a server with this bot or opted in. If you do not want to receive these messages, run `/set_announce_level <level>`)')
                    ids.append(int(user.id))
                    successfully_sent += 1
                except Exception:
                    error += 1

        await ctx.reply(f'Successfully sent to {successfully_sent} guild owners, {not_sent} not sent, {error} not sent due to error.')


async def setup(bot: KidneyBot):
    await bot.add_cog(Other(bot))
