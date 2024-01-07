# This cog creates all "fun" commands
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import random
import aiohttp
import logging
import pilcord
from bill import insult
import wikipedia
from faker import Faker
from faker.providers import internet, company, phone_number, passport, ssn


class Fun(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.rps_scenarios = [
            ['D', 'L', 'W'],
            ['W', 'D', 'L'],
            ['L', 'W', 'D'],
        ]

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info('Fun cog loaded.')

    @app_commands.command(name="yomama", description="get a yo mama joke")
    async def yomama(self, interaction: discord.Interaction):
        await interaction.response.defer()
        async with aiohttp.ClientSession() as cs:
            async with cs.get('https://api.yomomma.info/') as r:
                res = await r.json()  # returns dict
                await interaction.followup.send(res["joke"])

    @app_commands.command(name="dadjoke", description="get dad joked")
    async def dadjoke(self, interaction: discord.Interaction):
        await interaction.response.defer()
        async with aiohttp.ClientSession() as cs:
            async with cs.get('https://icanhazdadjoke.com/', headers={"Accept": "application/json"}) as r:
                res = await r.json()
                await interaction.followup.send(res["joke"])

    @app_commands.command(name="dog", description="dog pic")
    async def dog(self, interaction: discord.Interaction):
        await interaction.response.defer()
        async with aiohttp.ClientSession() as cs:
            async with cs.get('https://dog.ceo/api/breeds/image/random') as r:
                res = await r.json()
                await interaction.followup.send(res["message"])

    @app_commands.command(name="duck", description="get a duck pic")
    async def duck(self, interaction: discord.Interaction):
        await interaction.response.defer()
        async with aiohttp.ClientSession() as cs:
            async with cs.get('https://random-d.uk/api/random') as r:
                res = await r.json()
                await interaction.followup.send(res["url"])

    @app_commands.command(name="cat", description='cat pic')
    async def cat(self, interaction: discord.Interaction):
        await interaction.response.defer()
        async with aiohttp.ClientSession() as cs:
            async with cs.get('https://aws.random.cat/meow') as r:
                res = await r.json()
                await interaction.followup.send(res["file"])

    @app_commands.command(name="meme", description="🤣")
    async def meme(self, interaction: discord.Interaction):
        await interaction.response.defer()
        async with aiohttp.ClientSession() as cs:
            async with cs.get('https://meme-api.com/gimme') as r:
                res = await r.json()
                await interaction.followup.send(res["url"])

    @app_commands.command(name="joke", description="its just a joke??")
    async def joke(self, interaction: discord.Interaction):
        await interaction.response.defer()
        async with aiohttp.ClientSession() as cs:
            async with cs.get('https://v2.jokeapi.dev/joke/Any?blacklistFlags=nsfw,racist,sexist,explicit&type=single') as r:
                res = await r.json()
                await interaction.followup.send(res['joke'])

    @app_commands.command(name='8ball', description='get advice on anything')
    async def _8ball(self, interaction: discord.Interaction, question: str):
        responses = ['indeed', 'undoubtedly', 'no', 'dunno', 'indecisive', 'idk', 'go away',
                     'yes', 'nope', 'maybe', 'probably', 'probably not', "don't count on it", 'ask again later', "yesn't"]
        await interaction.response.send_message(f'> {question}\n:8ball: {random.choice(responses)}')

    @app_commands.command(name='rps', description='play rps for a chance to win beans')
    async def rps(self, interaction: discord.Interaction):
        await interaction.response.send_message('Send R for :rock:, send P for :scroll:, send S for :scissors:')

        def check(m):
            return m.content.lower() in ['r', 'p', 's'] and m.channel == interaction.channel and m.author == interaction.user

        message: discord.Message = await self.bot.wait_for('message', check=check, timeout=15)
        player = ['r', 'p', 's'].index(message.content.lower())
        while True:
            computer = random.randint(0, 2)
            if self.rps_scenarios[player][computer] == 'L':
                if random.randint(0, 2) == 0:
                    break
                else:
                    continue
            elif self.rps_scenarios[player][computer] in ['W', 'D']:
                break
        # Check the table for the outcome
        outcome = self.rps_scenarios[player][computer]

        if outcome == 'W':
            await message.reply('You win! +50 beans')
            await self.bot.add_currency(message.author, 50, 'wallet')
        elif outcome == 'L':
            await message.reply('I win!')
        elif outcome == 'D':
            await message.reply('Draw!')

    @app_commands.command(name='fight_under_this_flag', description='fight under this flag meme')
    @app_commands.checks.cooldown(1, 5, key=lambda i: i.user.id)
    async def fight_under_this_flag(self, interaction: discord.Interaction, user: discord.Member = None, flag: discord.Attachment = None, flag_url: str = None):
        await interaction.response.defer()
        # Count how many arguments are not None
        num_arguments = sum(arg is not None for arg in [user, flag, flag_url])

        # Check if only one argument is set
        if num_arguments > 1:
            await interaction.followup.send('You must provide exactly one of the arguments: user, flag, or flag_url.', ephemeral=True)
            return

        if user is None and flag is None and flag_url is None:
            image = interaction.user.avatar.url
        if user is not None:
            image = user.avatar.url
        if flag is not None:
            image = flag.url
        if flag_url is not None:
            image = flag_url

        await interaction.response.defer()
        a = pilcord.Meme(avatar=image)
        await interaction.followup.send(file=discord.File(await a.fight_under_this_flag(), filename='fight_under_this_flag.png'))

    @app_commands.command(name='uwu_discord', description='uwu discord meme')
    @app_commands.checks.cooldown(1, 5, key=lambda i: i.user.id)
    async def uwu_discord(self, interaction: discord.Interaction, user: discord.Member = None, flag: discord.Attachment = None, flag_url: str = None):
        await interaction.response.defer()
        if user is None and flag is None and flag_url is None:
            image = interaction.user.avatar.url
        elif user is not None and flag is None and flag_url is None:
            image = user.avatar.url
        elif user is None and flag is not None and flag_url is None:
            image = flag.url
        elif user is None and flag is None and flag_url is not None:
            image = flag_url
        else:
            await interaction.followup.send('Something went wrong, please try again', ephemeral=True)
            return
        await interaction.response.defer()
        a = pilcord.Meme(avatar=image)
        await interaction.followup.send(file=discord.File(await a.uwu_discord(), filename='uwu_discord.png'))

    @app_commands.command(name='rip', description='rip meme')
    @app_commands.checks.cooldown(1, 5, key=lambda i: i.user.id)
    async def rip(self, interaction: discord.Interaction, user: discord.Member = None, flag: discord.Attachment = None, flag_url: str = None):
        await interaction.response.defer()
        if user is None and flag is None and flag_url is None:
            image = interaction.user.avatar.url
        elif user is not None and flag is None and flag_url is None:
            image = user.avatar.url
        elif user is None and flag is not None and flag_url is None:
            image = flag.url
        elif user is None and flag is None and flag_url is not None:
            image = flag_url
        else:
            await interaction.followup.send('Something went wrong, please try again', ephemeral=True)
            return
        await interaction.response.defer()
        a = pilcord.Meme(avatar=image)
        await interaction.followup.send(file=discord.File(await a.rip(), filename='rip.png'))

    @app_commands.command(name='synonym', description='get a synonym')
    async def synonym(self, interaction: discord.Interaction, word: str):
        await interaction.response.defer()
        async with aiohttp.ClientSession() as cs:
            async with cs.get(f'https://api.datamuse.com/words?rel_syn={word}') as r:
                res = await r.json()
                words = []
                for i in res:
                    if len(words) < 10:
                        words.append(i['word'])
                    else:
                        break
                await interaction.followup.send(f"Synonyms for {word}:\n{', '.join(words)}")

    @app_commands.command(name='antonym', description='get an antonym')
    async def antonym(self, interaction: discord.Interaction, word: str):
        await interaction.response.defer()
        async with aiohttp.ClientSession() as cs:
            async with cs.get(f'https://api.datamuse.com/words?rel_ant={word}') as r:
                res = await r.json()
                words = []
                for i in res:
                    if len(words) < 10:
                        words.append(i['word'])
                    else:
                        break
                await interaction.followup.send(f"Antonyms for {word}:\n{', '.join(words)}")

    @app_commands.command(name='shakespearean-insult', description='get a shakespearean insult')
    async def shakespearean_insult(self, interaction: discord.Interaction):
        await interaction.response.send_message(insult())

    @app_commands.command(name='wikipedia', description='get a wikipedia article')
    @app_commands.checks.cooldown(1, 5, key=lambda i: i.user.id)
    async def wikipedia(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        try:
            page: wikipedia.WikipediaPage = await asyncio.to_thread(wikipedia.page, title=query)
            text = page.summary[:1000]
            if len(page.summary) > 1000:
                text += '...'

            embed = discord.Embed(title=page.title, description=text, url=page.url)
            embed.set_image(url=page.images[0])
            embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.avatar.url)
            await interaction.followup.send(embed=embed)
        except wikipedia.exceptions.DisambiguationError as e:
            options = []
            for i in e.options:
                if len(options) < 10:
                    options.append(i)
                else:
                    break
            await interaction.followup.send(f"Could not determine what you meant, please be more specific. Here are some options:\n{', '.join(options)}", ephemeral=True)
        except wikipedia.exceptions.PageError:
            await interaction.followup.send("Could not find that page.", ephemeral=True)

    @app_commands.command(name="fake-info", description="get fake info")
    async def fake_info(self, interaction: discord.Interaction):
        fake = Faker(use_weighting=False)
        fake.add_provider(internet)
        fake.add_provider(company)
        fake.add_provider(phone_number)
        fake.add_provider(passport)
        fake.add_provider(ssn)

        await interaction.response.send_message(f"""**Fake Information**
Name: {fake.name()}
Address: {', '.join(fake.address().splitlines())}
Email: {fake.email()}
IP Address: {fake.ipv4()}
Company: {fake.company()}
Phone Number: {fake.phone_number()}
Passport Number: {fake.passport_number()}
SSN: {fake.ssn()}""")


async def setup(bot):
    await bot.add_cog(Fun(bot))
