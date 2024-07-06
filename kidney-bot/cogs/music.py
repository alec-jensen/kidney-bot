# This cog creates all music commands
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md
import time

import discord
from discord.ext import commands
from discord import app_commands
import youtube_dl
import pafy
import asyncio
import logging
import traceback

from utils.kidney_bot import KidneyBot


class Music(commands.Cog):

    def __init__(self, bot):
        self.bot: KidneyBot = bot

        self.song_queue: dict[int, list[pafy.pafy.Pafy]] = {}

        self.stale_channels: dict[int, int] = {}

        asyncio.create_task(self.stale_channel_checker())

    async def stale_channel_checker(self):
        while True:
            try:
                for client in self.bot.voice_clients:
                    member: discord.Member
                    stale = False
                    for member in client.channel.members:
                        if not member.bot:
                            stale = True
                            break

                    if not stale:
                        if client.channel.id not in self.stale_channels.keys():
                            self.stale_channels[client.channel.id] = time.time()
                        else:
                            if time.time() - self.stale_channels.get(client.channel.id, 0) > 300:
                                await client.disconnect(force=True)
                                del self.stale_channels[client.channel.id]
                    else:
                        if client.channel.id in self.stale_channels.keys():
                            del self.stale_channels[client.channel.id]

                for channel_id in self.stale_channels.keys():
                    if time.time() - self.stale_channels[channel_id] > 300:
                        del self.stale_channels[channel_id]

            except Exception as e:
                logging.error(f"Error in stale channel checker: {e}")
                logging.error(traceback.format_exc())

            await asyncio.sleep(60)


    @commands.Cog.listener()
    async def on_ready(self):
        logging.info('Music cog loaded.')

    async def basic_checks(self, interaction: discord.Interaction):
        if interaction.guild.voice_client is None:
            return await interaction.response.send_message("I am not playing any song.", ephemeral=True)
        if interaction.user.voice is None:
            return await interaction.response.send_message("You are not connected to any voice channel.",
                                                           ephemeral=True)
        if interaction.user.voice.channel.id != interaction.guild.voice_client.channel.id:
            return await interaction.response.send_message("I am not currently playing any songs for you.",
                                                           ephemeral=True)
        else:
            return True

    async def check_queue(self, interaction: discord.Interaction):
        try:
            if len(self.song_queue[interaction.guild.id]) > 0:
                interaction.guild.voice_client.stop()
                await self.play_song(interaction, self.song_queue[interaction.guild.id][0])
                self.song_queue[interaction.guild.id].pop(0)
        except:
            pass

    async def search_song(self, song, get_url=False):
        info = await self.bot.loop.run_in_executor(None,
                                                   lambda: youtube_dl.YoutubeDL({"format": "bestaudio"}).extract_info(
                                                       f"ytsearch1:{song}", download=False, ie_key="YoutubeSearch"))
        try:
            if len(info["entries"]) == 0:
                return None
        except:
            return None
        return [entry["webpage_url"] for entry in info["entries"]] if get_url else info

    async def play_song(self, interaction: discord.Interaction, song: pafy.pafy.Pafy):
        voice: discord.VoiceProtocol = interaction.guild.voice_client
        if not voice or not voice.channel:
            await interaction.user.voice.channel.connect()
            voice = interaction.guild.voice_client
        url = song.getworstaudio().url
        voice.play(discord.FFmpegPCMAudio(url, before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"),
                   after=lambda e: self.bot.loop.create_task(self.check_queue(interaction)))
        voice.source.volume = 0.5

    @app_commands.command(name='play', description='Play a song (BUGGY; MAY NOT WORK FOR SOME QUERIES)')
    @app_commands.checks.cooldown(1, 10, key=lambda i: i.user.id)
    @app_commands.guild_only()
    async def play(self, interaction: discord.Interaction, *, song: str):
        if not interaction.user.voice:
            await interaction.response.send_message('You must be connected to a voice channel to use this command!',
                                                    ephemeral=True)
            return
        voice = interaction.guild.voice_client
        if not voice:
            await interaction.user.voice.channel.connect()
            voice = interaction.guild.voice_client
        await interaction.response.send_message("Searching for song, this may take a few seconds.")

        if not ("youtube.com" in song or "youtu.be" in song):
            result = await self.search_song(song, get_url=True)
            if result is None:
                await interaction.edit_original_response(content="I couldn't find that song!")
                return
            song = result[0]

        psong = await self.bot.loop.run_in_executor(None, lambda: pafy.new(song))

        if voice.is_playing():
            self.song_queue[interaction.guild.id].append(psong)
            await interaction.edit_original_response(
                content=f"I am currently playing a song, {song} has been added to the queue at position: {len(self.song_queue)}.")
        else:
            self.song_queue[interaction.guild.id] = []
            await self.play_song(interaction, psong)
            await interaction.edit_original_response(content=f"Now playing: {song}")

    @app_commands.command(name='leave', description='Have the bot leave the current voice channel.')
    @app_commands.guild_only()
    async def leave(self, interaction: discord.Interaction):
        if not await self.basic_checks(interaction):
            return
        voice = discord.utils.get(
            self.bot.voice_clients, guild=interaction.guild)
        if voice.is_connected():
            try:
                del self.song_queue[interaction.guild.id]
            except KeyError:
                pass
            await voice.disconnect()
            await interaction.response.send_message('Left voice channel.', ephemeral=True)
        else:
            await interaction.response.send_message("I am not in any voice channel!", ephemeral=True)

    @app_commands.command(name='pause', description='Pause the currently playing song')
    @app_commands.guild_only()
    async def pause(self, interaction: discord.Interaction):
        if not await self.basic_checks(interaction):
            return
        voice = interaction.guild.voice_client
        if voice.is_playing():
            voice.pause()
            await interaction.response.send_message('Paused.', ephemeral=True)
        else:
            interaction.response.send_message(
                "No audio is playing.", ephemeral=True)

    @app_commands.command(name='resume', description='Resume playing the current song')
    @app_commands.guild_only()
    async def resume(self, interaction: discord.Interaction):
        if not await self.basic_checks(interaction):
            return
        voice = interaction.guild.voice_client
        if voice.is_paused():
            voice.resume()
            await interaction.response.send_message('Resumed.', ephemeral=True)
        else:
            interaction.response.send_message(
                "No audio is paused.", ephemeral=True)

    @app_commands.command(name='stop', description='Stop playing the current song')
    @app_commands.guild_only()
    async def stop(self, interaction: discord.Interaction):
        if not await self.basic_checks(interaction):
            return
        voice = interaction.guild.voice_client
        voice.stop()
        try:
            del self.song_queue[interaction.guild.id]
        except KeyError:
            pass
        await interaction.response.send_message('Stopped.', ephemeral=True)

    @app_commands.command(name='queue', description='See the songs in the queue')
    @app_commands.guild_only()
    async def queue(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if not await self.basic_checks(interaction):
            return
        try:
            self.song_queue[interaction.guild.id]
        except:
            self.song_queue[interaction.guild.id] = []
        if len(self.song_queue[interaction.guild.id]) == 0:
            return await interaction.followup.send("There are currently no songs in the queue.", ephemeral=True)
        embed = discord.Embed(
            title="Song Queue", description="\u200b", colour=discord.Colour.blue())
        for i, song in enumerate(self.song_queue[interaction.guild.id]):
            embed.description += f"{i+1}) [{song.title}](https://www.youtube.com/watch?v={song.videoid})\n"
        embed.set_footer(text=interaction.user,
                         icon_url=interaction.user.avatar.url)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name='skip', description='Skip the current song')
    @app_commands.guild_only()
    async def skip(self, interaction):
        if not await self.basic_checks(interaction):
            return
        vc = interaction.user.voice.channel
        if len(vc.members) <= 1:
            skip = True
            await interaction.response.send_message('Skipping.')
        else:
            poll = discord.Embed(title=f"Vote to Skip Song by {interaction.user.name}#{interaction.user.discriminator}",
                                 description="**>50% of the voice channel must vote to skip for it to pass.**",
                                 colour=discord.Colour.blue())
            poll.add_field(name="Skip", value=":white_check_mark:")
            poll.add_field(name="Stay", value=":no_entry_sign:")
            poll.add_field(name="Voting ends",
                           value=f"<t:{int(time.time() + 15)}:R>", inline=False)
            await interaction.response.send_message(embed=poll)
            poll_msg = await interaction.original_response()
            await poll_msg.add_reaction(u"\u2705")  # yes
            await poll_msg.add_reaction(u"\U0001F6AB")  # no
            await asyncio.sleep(15)
            votes = {u"\u2705": 0, u"\U0001F6AB": 0}
            reacted = []
            poll_msg = await interaction.followup.fetch_message(poll_msg.id)
            for reaction in poll_msg.reactions:
                if reaction.emoji in [u"\u2705", u"\U0001F6AB"]:
                    async for user in reaction.users():
                        member = await interaction.guild.fetch_member(user.id)
                        if not user.bot and member.voice.channel.id == interaction.guild.voice_client.channel.id and member.id not in reacted:
                            votes[reaction.emoji] += 1
                            reacted.append(user.id)
            skip = False
            if votes[u"\u2705"] > 0:
                if votes[u"\U0001F6AB"] == 0 or votes[u"\u2705"] / (
                        votes[u"\u2705"] + votes[u"\U0001F6AB"]) > 0.5:  # 50% or higher
                    skip = True
                    embed = discord.Embed(title="Skip Successful",
                                          description="***Voting to skip the current song was succesful, skipping now.***",
                                          colour=discord.Colour.green())
            if not skip:
                embed = discord.Embed(title="Skip Failed",
                                      description="*Voting to skip the current song has failed.*\n\n**Voting failed, the vote requires at least 50% of the members to skip.**",
                                      colour=discord.Colour.red())
            embed.set_footer(text="Voting has ended.")
            await poll_msg.clear_reactions()
            await interaction.edit_original_response(embed=embed)
        if skip:
            interaction.guild.voice_client.stop()
            await self.check_queue(interaction)

    @app_commands.command(name='forceskip', description="Force skip song.")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def forceskip(self, interaction: discord.Interaction):
        if not await self.basic_checks(interaction):
            return
        await interaction.response.send_message("Song force skipped.")
        interaction.guild.voice_client.stop()
        await self.check_queue(interaction)

    @app_commands.command(name='remove', description='Remove song from the queue')
    @app_commands.default_permissions(manage_messages=True)
    async def remove(self, interaction: discord.Interaction, index: int):
        if not await self.basic_checks(interaction):
            return
        try:
            self.song_queue[interaction.guild.id].pop(index - 1)
            await interaction.response.send_message("Removed song.")
        except IndexError:
            await interaction.response.send_message("Index is out of range!", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Music(bot))
