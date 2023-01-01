# This cog creates all ActiveGuard features
# Copyright (C) 2022  Alec Jensen
# Full license at LICENSE.md

import time
import discord
from discord.ext import commands
from discord import app_commands
from typing import Literal
import uuid
import logging


class ReportView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Accept', style=discord.ButtonStyle.green, custom_id='report:accept')
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        report_id = interaction.message.embeds[0].footer.text.split('`')[1]
        bot = interaction.client
        report = await bot.database.reports.find_one({"report_id": report_id})
        if report["report_status"] is not None:
            await bot.database.reports.update_one({"report_id": report_id},
                                                       {"$set": {"report_status": "accetped", "handled_by": interaction.user.id}})
        elif interaction.user.id == bot.config.owner_id:
            await bot.database.reports.update_one({"report_id": report_id},
                                                       {"$set": {"report_status": "accetped", "handled_by": interaction.user.id}})

        if report["report_status"] is not None or interaction.user.id == bot.config.owner_id:
            doc = await bot.database.scammer_list.find_one({"user": report["reported_user"]})
            if doc is None:
                await bot.database.scammer_list.insert_one({
                    "user": report["reported_user"],
                    "time": time.time(),
                    "reason": report["reason"]
                })

        try:
            await bot.get_user(report["reporter"]).send(f"Your report on **{report['reported_user_name']}** has been accepted.")
        except:
            pass
        try:
            await bot.get_user(report['reported_user']).send("You have been added to kidney bot's scammer blacklist. You can appeal this in our support server. https://discord.com/invite/TsuZCbz5KD")
        except:
            pass

        embed = interaction.message.embeds[0]
        embed.add_field(name='✅', value=f'Accepted by {interaction.user}', inline=False)
        await interaction.message.edit(embed=embed)
        await interaction.response.send_message('Report accepted.', ephemeral=True)

        async for message in bot.get_channel(bot.config.report_channel).history(limit=1000):
            report_id = message.embeds[0].footer.text.split('`')[1]
            doc = await bot.database.reports.find_one({"report_id": report_id})
            if doc is not None:
                if doc['reported_user'] == report['reported_user'] and doc['report_status'] == None:
                    embed = interaction.message.embeds[0]
                    embed.add_field(name='❕', value=f'User is on blacklist.', inline=False)
                    await message.edit(embed=embed)

    @discord.ui.button(label='Deny', style=discord.ButtonStyle.red, custom_id='report:deny')
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        report_id = interaction.message.embeds[0].footer.text.split('`')[1]
        bot = interaction.client
        report = await bot.database.reports.find_one({"report_id": report_id})
        if report["report_status"] is not None:
            await bot.database.reports.update_one({"report_id": report_id},
                                                       {"$set": {"report_status": "denied", "handled_by": interaction.user.id}})
        elif interaction.user.id == bot.config.owner_id:
            await bot.database.reports.update_one({"report_id": report_id},
                                                       {"$set": {"report_status": "denied"}})

        doc = await bot.database.scammer_list.find_one({"user": report["reported_user"]})
        if doc is not None:
            await bot.database.scammer_list.delete_one(doc)

        try:
            await bot.get_user(report["reporter"]).send(f"Your report on **{report['reported_user_name']}** has been denied.")
        except:
            pass
        embed = interaction.message.embeds[0]
        embed.add_field(name='❌', value=f'Denied by {interaction.user}', inline=False)
        await interaction.message.edit(embed=embed)
        await interaction.response.send_message('Report denied.', ephemeral=True)


class ActiveGuard(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info('ActiveGuard cog loaded.')

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        member = message.guild.fetch_member(message.author.id)
        doc = await self.bot.database.activeguardsettings.find_one({"guild": member.guild.id})
        if doc is not None and doc.get('block_known_spammers') is True:
            doc = await self.bot.database.scammer_list.find_one({"user": member.id})
            if doc is not None:
                await member.send(f'You have been banned from {member.guild.name} for being on the global blacklist. You can appeal this in our support server. https://discord.com/invite/TsuZCbz5KD')
                await member.ban(reason="User is on global blacklist.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        doc = await self.bot.database.activeguardsettings.find_one({"guild": member.guild.id})
        if doc is not None and doc.get('block_known_spammers') is True:
            doc = await self.bot.database.scammer_list.find_one({"user": member.id})
            if doc is not None:
                await member.send(f'You have been banned from {member.guild.name} for being on the global blacklist. You can appeal this in our support server. https://discord.com/invite/TsuZCbz5KD')
                await member.ban(reason="User is on global blacklist.")

    active_guard = app_commands.Group(name='activeguard', description='Manage ActiveGuard settings',
                                      default_permissions=discord.Permissions(manage_guild=True))

    @active_guard.command(name='block_spammers', description='Should ActiveGuard block known spammers?')
    async def block_known_spammers(self, interaction: discord.Interaction, state: Literal['on', 'off']):
        # Check if the guild has a document in the database, if not create one
        if await self.bot.database.activeguardsettings.find_one({"guild_id": interaction.guild.id}) is None:
            await self.bot.database.activeguardsettings.insert_one({"guild_id": interaction.guild.id})

        if state == 'on':
            await self.bot.database.activeguardsettings.update_one({"guild_id": interaction.guild.id},
                                                      {"$set": {"block_known_spammers": True}})
            await interaction.response.send_message('ActiveGuard will now block known spammers.', ephemeral=True)
        else:
            await self.bot.database.activeguardsettings.update_one({"guild_id": interaction.guild.id},
                                                      {"$set": {"block_known_spammers": False}})
            await interaction.response.send_message('ActiveGuard will no longer block known spammers.', ephemeral=True)

    @app_commands.command(name='report', description='report scammers')
    async def report_command(self, interaction: discord.Interaction, user: discord.User, reason: str,
                             message_id: int = None):
        report_id = uuid.uuid4()
        message = interaction.channel.fetch_message(message_id) if message_id is not None else None
        if message is not None and message.author != user:
            interaction.response.send_message('The provided message isn\'t from the user whom you are trying to report!', ephemeral=True)
            return
        doc = await self.bot.database.scammer_list.find_one({"user": user.id})
        if doc is not None:
            await interaction.response.send_message('User already blacklisted.', ephemeral=True)
            return
        embed = discord.Embed(title=f'{interaction.user} has submitted a report!', color=discord.Color.red())
        embed.add_field(name=f'Suspect: {user.name}#{user.discriminator}({user.id})',
                        value=f'Reason: ```{reason}```' +
                              (f'\nReported message: ```{message.content}```\n'
                               f'Message attachments: {message.attachments}' if message is not None else ''))
        embed.set_footer(text=f'Report ID: `{report_id}`')
        await self.bot.get_channel(self.bot.config.report_channel).send(embed=embed, view=ReportView())
        await self.bot.database.reports.insert_one({
            "report_id": str(report_id),
            "reporter": interaction.user.id,
            "time_reported": time.time(),
            "reported_user": user.id,
            "reported_user_name": f"{user}#{user.discriminator}",
            "reason": reason,
            "attached_message": message.content if message is not None else None,
            "attached_message_attachments": message.attachments if message is not None else None,
            "report_status": None,
            "handled_by": None
        })
        await interaction.response.send_message('Report submitted! Thank you.', ephemeral=True)


async def setup(bot):
    await bot.add_cog(ActiveGuard(bot))
