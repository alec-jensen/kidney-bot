import discord
from discord.ext import commands
import youtube_dl
import pafy
import asyncio

queue = {}


class Music(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print('Music cog loaded.')

    async def check_queue(self, ctx):
        try:
            if len(queue[ctx.guild.id]) > 0:
                ctx.voice_client.stop()
                await self.play_song(ctx, queue[ctx.guild.id][0])
                queue[ctx.guild.id].pop(0)
        except:
            pass

    async def search_song(self, song, get_url=False):
        info = await self.bot.loop.run_in_executor(None,
                                                   lambda: youtube_dl.YoutubeDL({"format": "bestaudio"}).extract_info(
                                                       f"ytsearch1:{song}", download=False, ie_key="YoutubeSearch"))
        try:
            if len(info["entries"]) == 0: return None
        except:
            return None
        return [entry["webpage_url"] for entry in info["entries"]] if get_url else info

    async def play_song(self, ctx, song):
        voice = ctx.voice_client
        if not voice:
            await ctx.author.voice.channel.connect()
            voice = ctx.voice_client
        url = pafy.new(song).getbestaudio().url
        voice.play(discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(url)),
                   after=lambda error: self.bot.loop.create_task(self.check_queue(ctx)))
        ctx.voice_client.source.volume = 0.5
        # old method, used when pafy was broken!
        """
        YDL_OPTIONS = {'format': 'bestaudio/best', 'noplaylist':'True'}
        with YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(song, download=False)
            I_URL = info['formats'][0]['url']
            voice.play(discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(I_URL)), after=lambda error: self.bot.loop.create_task(self.check_queue(ctx)))
            ctx.voice_client.source.volume = 0.3"""

    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def play(self, ctx, *, song: str):
        if not ctx.author.voice:
            await ctx.reply('You must be connected to a voice channel to use this command!')
            return
        voice = ctx.voice_client
        if not voice:
            await ctx.author.voice.channel.connect()
            voice = ctx.voice_client
        if not ("youtube.com/watch?" in song or "https://youtu.be/" in song):
            message = await ctx.reply("Searching for song, this may take a few seconds.")
            result = await self.search_song(song, get_url=True)
            if result is None:
                return await ctx.send("I couldn't find that song!")
            song = result[0]
        else:
            message = await ctx.message.reply("Playing song.")
        if voice.is_playing():
            queue_len = len(queue[ctx.guild.id])
            queue[ctx.guild.id].append(song)
            await message.edit(
                content=f"I am currently playing a song, {song} has been added to the queue at position: {queue_len + 1}.")
        else:
            queue[ctx.guild.id] = []
            await self.play_song(ctx, song)
            await message.edit(content=f"Now playing: {song}")

    @commands.command()
    async def leave(self, ctx):
        voice = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
        if voice.is_connected():
            try:
                del queue[ctx.guild.id]
            except KeyError:
                pass
            await voice.disconnect()
        else:
            await ctx.reply("I am not in any voice channel!")

    @commands.command()
    async def pause(self, ctx):
        voice = ctx.voice_client
        if voice.is_playing():
            voice.pause()
        else:
            ctx.send("No audio is playing.")

    @commands.command(aliases=['unpause', 'continue'])
    async def resume(self, ctx):
        voice = ctx.voice_client
        if voice.is_paused():
            voice.resume()
        else:
            ctx.reply("No audio is paused.")

    @commands.command()
    async def stop(self, ctx):
        voice = ctx.voice_client
        voice.stop()
        try:
            del queue[ctx.guild.id]
        except KeyError:
            pass

    @commands.command()
    async def queue(self, ctx):
        try:
            queue[ctx.guild.id]
        except:
            queue[ctx.guild.id] = []
        if len(queue[ctx.guild.id]) == 0:
            return await ctx.reply("There are currently no songs in the queue.")
        embed = discord.Embed(title="Song Queue", description="\u200b", colour=discord.Colour.blue())
        i = 1
        for url in queue[ctx.guild.id]:
            embed.description += f"{i}) [{pafy.new(url).title}]({url})\n"
            i += 1
        embed.set_footer(text=ctx.author, icon_url=ctx.author.avatar_url)
        await ctx.send(embed=embed)

    @commands.command()
    async def skip(self, ctx):
        if ctx.voice_client is None:
            return await ctx.send("I am not playing any song.")
        if ctx.author.voice is None:
            return await ctx.send("You are not connected to any voice channel.")
        if ctx.author.voice.channel.id != ctx.voice_client.channel.id:
            return await ctx.send("I am not currently playing any songs for you.")
        poll = discord.Embed(title=f"Vote to Skip Song by {ctx.author.name}#{ctx.author.discriminator}",
                             description="**80% of the voice channel must vote to skip for it to pass.**",
                             colour=discord.Colour.blue())
        poll.add_field(name="Skip", value=":white_check_mark:")
        poll.add_field(name="Stay", value=":no_entry_sign:")
        poll.set_footer(text="Voting ends in 15 seconds.")
        poll_msg = await ctx.send(embed=poll)
        poll_id = poll_msg.id
        await poll_msg.add_reaction(u"\u2705")  # yes
        await poll_msg.add_reaction(u"\U0001F6AB")  # no
        await asyncio.sleep(15)
        poll_msg = await ctx.channel.fetch_message(poll_id)
        votes = {u"\u2705": 0, u"\U0001F6AB": 0}
        reacted = []
        for reaction in poll_msg.reactions:
            if reaction.emoji in [u"\u2705", u"\U0001F6AB"]:
                async for user in reaction.users():
                    if user.voice.channel.id == ctx.voice_client.channel.id and user.id not in reacted and not user.bot:
                        votes[reaction.emoji] += 1
                        reacted.append(user.id)
        skip = False
        if votes[u"\u2705"] > 0:
            if votes[u"\U0001F6AB"] == 0 or votes[u"\u2705"] / (
                    votes[u"\u2705"] + votes[u"\U0001F6AB"]) > 0.79:  # 80% or higher
                skip = True
                embed = discord.Embed(title="Skip Successful",
                                      description="***Voting to skip the current song was succesful, skipping now.***",
                                      colour=discord.Colour.green())
        if not skip:
            embed = discord.Embed(title="Skip Failed",
                                  description="*Voting to skip the current song has failed.*\n\n**Voting failed, the vote requires at least 80% of the members to skip.**",
                                  colour=discord.Colour.red())
        embed.set_footer(text="Voting has ended.")
        await poll_msg.clear_reactions()
        await poll_msg.edit(embed=embed)
        if skip:
            ctx.voice_client.stop()
            await self.check_queue(ctx)

    @commands.command(aliases=['fskip'], brief="Force skip",
                      help="Force skip song. Requires `Manage Messages` permission")
    @commands.has_permissions(manage_messages=True)
    async def forceskip(self, ctx):
        ctx.message.delete()
        await ctx.send("Song force skipped.")
        ctx.voice_client.stop()
        await self.check_queue(ctx)

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def remove(self, ctx, index: int):
        try:
            queue[ctx.guild.id].pop(index - 1)
            await ctx.reply("Removed song.")
        except IndexError:
            await ctx.reply("Index is out of range!")


async def setup(bot):
    await bot.add_cog(Music(bot))
