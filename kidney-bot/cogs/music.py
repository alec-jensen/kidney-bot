# This cog creates all music commands
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md
import time
from typing import Any, Dict, List, Optional, cast

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

        self.song_queue: Dict[int, List[Any]] = {}  # type: ignore

        self.stale_channels: Dict[int, float] = {}

        asyncio.create_task(self.stale_channel_checker())

    async def stale_channel_checker(self):
        while True:
            try:
                for client in self.bot.voice_clients:
                    if not isinstance(client.channel, discord.VoiceChannel):
                        continue
                    
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

                channels_to_delete = []
                for channel_id in self.stale_channels.keys():
                    if time.time() - self.stale_channels[channel_id] > 300:
                        channels_to_delete.append(channel_id)
                
                for channel_id in channels_to_delete:
                    del self.stale_channels[channel_id]

            except Exception as e:
                logging.error(f"Error in stale channel checker: {e}")
                logging.error(traceback.format_exc())

            await asyncio.sleep(60)


    @commands.Cog.listener()
    async def on_ready(self):
        logging.info('Music cog loaded.')

    async def basic_checks(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return False
        
        if interaction.guild.voice_client is None:
            await interaction.response.send_message("I am not playing any song.", ephemeral=True)
            return False
        
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This command can only be used by server members.", ephemeral=True)
            return False
            
        if interaction.user.voice is None:
            await interaction.response.send_message("You are not connected to any voice channel.", ephemeral=True)
            return False
        
        if interaction.user.voice.channel is None:
            await interaction.response.send_message("You are not connected to any voice channel.", ephemeral=True)
            return False
            
        voice_client = interaction.guild.voice_client
        if not hasattr(voice_client, 'channel') or voice_client.channel is None:
            await interaction.response.send_message("I am not connected to a voice channel.", ephemeral=True)
            return False
            
        if interaction.user.voice.channel.id != voice_client.channel.id:  # type: ignore
            await interaction.response.send_message("I am not currently playing any songs for you.", ephemeral=True)
            return False
        
        return True

    async def check_queue(self, interaction: discord.Interaction):
        try:
            if not interaction.guild:
                return
            
            guild_id = interaction.guild.id
            voice_client = interaction.guild.voice_client
            
            if guild_id in self.song_queue and len(self.song_queue[guild_id]) > 0:
                if voice_client and hasattr(voice_client, 'stop'):
                    voice_client.stop()  # type: ignore
                await self.play_song(interaction, self.song_queue[guild_id][0])
                self.song_queue[guild_id].pop(0)
        except:
            pass

    async def search_song(self, song: str, get_url: bool = False) -> Optional[Any]:
        try:
            info = await self.bot.loop.run_in_executor(None,
                                                       lambda: youtube_dl.YoutubeDL({"format": "bestaudio"}).extract_info(
                                                           f"ytsearch1:{song}", download=False, ie_key="YoutubeSearch"))
            if not info or not isinstance(info, dict) or "entries" not in info:
                return None
            
            if len(info["entries"]) == 0:
                return None
                
            return [entry["webpage_url"] for entry in info["entries"]] if get_url else info
        except:
            return None

    async def play_song(self, interaction: discord.Interaction, song: Any):
        if not interaction.guild:
            return
            
        voice_client = interaction.guild.voice_client
        
        if not voice_client or not hasattr(voice_client, 'channel') or voice_client.channel is None:
            if not isinstance(interaction.user, discord.Member) or not interaction.user.voice or not interaction.user.voice.channel:
                return
            await interaction.user.voice.channel.connect()
            voice_client = interaction.guild.voice_client
            
        if not voice_client:
            return
        
        try:
            url = song.getworstaudio().url  # type: ignore
            voice_client.play(discord.FFmpegPCMAudio(url, before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"),  # type: ignore
                           after=lambda e: self.bot.loop.create_task(self.check_queue(interaction)))
            if hasattr(voice_client, 'source') and voice_client.source and hasattr(voice_client.source, 'volume'):  # type: ignore
                voice_client.source.volume = 0.5  # type: ignore
        except Exception as e:
            logging.error(f"Error playing song: {e}")

    @app_commands.command(name='play', description='Play a song (BUGGY; MAY NOT WORK FOR SOME QUERIES)')
    @app_commands.checks.cooldown(1, 10, key=lambda i: i.user.id)
    @app_commands.guild_only()
    async def play(self, interaction: discord.Interaction, *, song: str):
        if not isinstance(interaction.user, discord.Member) or not interaction.user.voice:
            await interaction.response.send_message('You must be connected to a voice channel to use this command!',
                                                    ephemeral=True)
            return
        
        if not interaction.guild:
            await interaction.response.send_message('This command can only be used in a server!', ephemeral=True)
            return
            
        voice_client = interaction.guild.voice_client
        if not voice_client:
            if not interaction.user.voice.channel:
                await interaction.response.send_message('You must be connected to a voice channel!', ephemeral=True)
                return
            await interaction.user.voice.channel.connect()
            voice_client = interaction.guild.voice_client
            
        await interaction.response.send_message("Searching for song, this may take a few seconds.")

        if not ("youtube.com" in song or "youtu.be" in song):
            result = await self.search_song(song, get_url=True)
            if result is None or not isinstance(result, list) or len(result) == 0:
                await interaction.edit_original_response(content="I couldn't find that song!")
                return
            song = result[0]

        try:
            psong = await self.bot.loop.run_in_executor(None, lambda: pafy.new(song))
        except Exception as e:
            await interaction.edit_original_response(content=f"Error loading song: {e}")
            return

        guild_id = interaction.guild.id
        
        if voice_client and hasattr(voice_client, 'is_playing') and voice_client.is_playing():  # type: ignore
            if guild_id not in self.song_queue:
                self.song_queue[guild_id] = []
            self.song_queue[guild_id].append(psong)
            await interaction.edit_original_response(
                content=f"I am currently playing a song, {song} has been added to the queue at position: {len(self.song_queue[guild_id])}.")
        else:
            self.song_queue[guild_id] = []
            await self.play_song(interaction, psong)
            await interaction.edit_original_response(content=f"Now playing: {song}")

    @app_commands.command(name='leave', description='Have the bot leave the current voice channel.')
    @app_commands.guild_only()
    async def leave(self, interaction: discord.Interaction):
        if not await self.basic_checks(interaction):
            return
        
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
            
        voice = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        if voice and hasattr(voice, 'is_connected') and voice.is_connected():  # type: ignore
            try:
                guild_id = interaction.guild.id
                if guild_id in self.song_queue:
                    del self.song_queue[guild_id]
            except KeyError:
                pass
            await voice.disconnect(force=True)  # type: ignore
            await interaction.response.send_message('Left voice channel.', ephemeral=True)
        else:
            await interaction.response.send_message("I am not in any voice channel!", ephemeral=True)

    @app_commands.command(name='pause', description='Pause the currently playing song')
    @app_commands.guild_only()
    async def pause(self, interaction: discord.Interaction):
        if not await self.basic_checks(interaction):
            return
        
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
            
        voice_client = interaction.guild.voice_client
        if voice_client and hasattr(voice_client, 'is_playing') and voice_client.is_playing():  # type: ignore
            voice_client.pause()  # type: ignore
            await interaction.response.send_message('Paused.', ephemeral=True)
        else:
            await interaction.response.send_message("No audio is playing.", ephemeral=True)

    @app_commands.command(name='resume', description='Resume playing the current song')
    @app_commands.guild_only()
    async def resume(self, interaction: discord.Interaction):
        if not await self.basic_checks(interaction):
            return
        
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
            
        voice_client = interaction.guild.voice_client
        if voice_client and hasattr(voice_client, 'is_paused') and voice_client.is_paused():  # type: ignore
            voice_client.resume()  # type: ignore
            await interaction.response.send_message('Resumed.', ephemeral=True)
        else:
            await interaction.response.send_message("No audio is paused.", ephemeral=True)

    @app_commands.command(name='stop', description='Stop playing the current song')
    @app_commands.guild_only()
    async def stop(self, interaction: discord.Interaction):
        if not await self.basic_checks(interaction):
            return
        
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
            
        voice_client = interaction.guild.voice_client
        if voice_client and hasattr(voice_client, 'stop'):
            voice_client.stop()  # type: ignore
        
        try:
            guild_id = interaction.guild.id
            if guild_id in self.song_queue:
                del self.song_queue[guild_id]
        except KeyError:
            pass
        await interaction.response.send_message('Stopped.', ephemeral=True)

    @app_commands.command(name='queue', description='See the songs in the queue')
    @app_commands.guild_only()
    async def queue(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if not await self.basic_checks(interaction):
            return
        
        if not interaction.guild:
            await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
            return
            
        guild_id = interaction.guild.id
        
        try:
            if guild_id not in self.song_queue:
                self.song_queue[guild_id] = []
        except:
            self.song_queue[guild_id] = []
            
        if len(self.song_queue[guild_id]) == 0:
            return await interaction.followup.send("There are currently no songs in the queue.", ephemeral=True)
            
        embed = discord.Embed(title="Song Queue", description="", colour=discord.Colour.blue())
        
        for i, song in enumerate(self.song_queue[guild_id]):
            try:
                embed.description += f"{i+1}) [{song.title}](https://www.youtube.com/watch?v={song.videoid})\n"  # type: ignore
            except:
                embed.description = embed.description or ""
                embed.description += f"{i+1}) Song {i+1}\n"
                
        if not embed.description:
            embed.description = "\u200b"
            
        embed.set_footer(text=str(interaction.user),
                         icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name='skip', description='Skip the current song')
    @app_commands.guild_only()
    async def skip(self, interaction: discord.Interaction):
        if not await self.basic_checks(interaction):
            return
            
        if not isinstance(interaction.user, discord.Member) or not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message('You must be connected to a voice channel!', ephemeral=True)
            return
            
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
            
        vc = interaction.user.voice.channel
        skip = False
        
        if len(vc.members) <= 1:
            skip = True
            await interaction.response.send_message('Skipping.')
        else:
            poll = discord.Embed(title=f"Vote to Skip Song by {interaction.user.display_name}",
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
            
            voice_client = interaction.guild.voice_client
            if not voice_client or not hasattr(voice_client, 'channel') or voice_client.channel is None:
                await interaction.edit_original_response(content="I am not connected to a voice channel.")
                return
                
            for reaction in poll_msg.reactions:
                if reaction.emoji in [u"\u2705", u"\U0001F6AB"]:
                    async for user in reaction.users():
                        try:
                            member = await interaction.guild.fetch_member(user.id)
                            if (not user.bot and member.voice and member.voice.channel and 
                                member.voice.channel.id == voice_client.channel.id and  # type: ignore
                                member.id not in reacted):
                                votes[str(reaction.emoji)] += 1
                                reacted.append(user.id)
                        except:
                            continue
                            
            embed = None
            if votes[u"\u2705"] > 0:
                if votes[u"\U0001F6AB"] == 0 or votes[u"\u2705"] / (
                        votes[u"\u2705"] + votes[u"\U0001F6AB"]) > 0.5:
                    skip = True
                    embed = discord.Embed(title="Skip Successful",
                                          description="***Voting to skip the current song was successful, skipping now.***",
                                          colour=discord.Colour.green())
                          
            if not skip:
                embed = discord.Embed(title="Skip Failed",
                                      description="*Voting to skip the current song has failed.*\n\n**Voting failed, the vote requires at least 50% of the members to skip.**",
                                      colour=discord.Colour.red())
                                      
            if embed:
                embed.set_footer(text="Voting has ended.")
                await poll_msg.clear_reactions()
                await interaction.edit_original_response(embed=embed)
                
        if skip:
            voice_client = interaction.guild.voice_client
            if voice_client and hasattr(voice_client, 'stop'):
                voice_client.stop()  # type: ignore
            await self.check_queue(interaction)

    @app_commands.command(name='forceskip', description="Force skip song.")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def forceskip(self, interaction: discord.Interaction):
        if not await self.basic_checks(interaction):
            return
        
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
            
        await interaction.response.send_message("Song force skipped.")
        voice_client = interaction.guild.voice_client
        if voice_client and hasattr(voice_client, 'stop'):
            voice_client.stop()  # type: ignore
        await self.check_queue(interaction)

    @app_commands.command(name='remove', description='Remove song from the queue')
    @app_commands.default_permissions(manage_messages=True)
    async def remove(self, interaction: discord.Interaction, index: int):
        if not await self.basic_checks(interaction):
            return
        
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
            
        try:
            guild_id = interaction.guild.id
            if guild_id in self.song_queue:
                self.song_queue[guild_id].pop(index - 1)
                await interaction.response.send_message("Removed song.")
            else:
                await interaction.response.send_message("No songs in queue!", ephemeral=True)
        except IndexError:
            await interaction.response.send_message("Index is out of range!", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Music(bot))
