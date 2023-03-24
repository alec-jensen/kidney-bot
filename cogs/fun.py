# This cog creates all "fun" commands
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import discord
from discord.ext import commands
from discord import app_commands
import random
import aiohttp
import logging


class Fun(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.scenarios = [
            ['D', 'L', 'W'],
            ['W', 'D', 'L'],
            ['L', 'W', 'D'],
        ]

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info('Fun cog loaded.')

    @app_commands.command(name="yomama", description="get a yo mama joke")
    async def yomama(self, interaction: discord.Interaction):
        async with aiohttp.ClientSession() as cs:
            async with cs.get('https://api.yomomma.info/') as r:
                res = await r.json()  # returns dict
                await interaction.response.send_message(res["joke"])

    @app_commands.command(name="dadjoke", description="get dad joked")
    async def dadjoke(self, interaction: discord.Interaction):
        #result = requests.get('https://icanhazdadjoke.com/', headers={"Accept": "application/json"}).json()
        async with aiohttp.ClientSession() as cs:
            async with cs.get('https://icanhazdadjoke.com/', headers={"Accept": "application/json"}) as r:
                res = await r.json()
                await interaction.response.send_message(res["joke"])

    @app_commands.command(name="dog", description="dog pic")
    async def dog(self, interaction: discord.Interaction):
        #result = requests.get('https://dog.ceo/api/breeds/image/random').json()
        async with aiohttp.ClientSession() as cs:
            async with cs.get('https://dog.ceo/api/breeds/image/random') as r:
                res = await r.json()
                await interaction.response.send_message(res["message"])

    @app_commands.command(name="duck", description="get a duck pic")
    async def duck(self, interaction: discord.Interaction):
        #result = requests.get('https://random-d.uk/api/random').json()
        async with aiohttp.ClientSession() as cs:
            async with cs.get('https://random-d.uk/api/random') as r:
                res = await r.json()
                await interaction.response.send_message(res["url"])

    @app_commands.command(name="cat", description='cat pic')
    async def cat(self, interaction: discord.Interaction):
        #result = requests.get('https://aws.random.cat/meow').json()
        async with aiohttp.ClientSession() as cs:
            async with cs.get('https://aws.random.cat/meow') as r:
                res = await r.json()
                await interaction.response.send_message(res["file"])

    @app_commands.command(name="meme", description="🤣")
    async def meme(self, interaction: discord.Interaction):
        #result = requests.get('https://meme-api.herokuapp.com/gimme').json()
        async with aiohttp.ClientSession() as cs:
            async with cs.get('https://meme-api.herokuapp.com/gimme') as r:
                res = await r.json()
                await interaction.response.send_message(res["url"])

    @app_commands.command(name="joke", description="its just a joke??")
    async def joke(self, interaction: discord.Interaction):
        #result = requests.get('https://v2.jokeapi.dev/joke/Any').json()
        async with aiohttp.ClientSession() as cs:
            async with cs.get('https://v2.jokeapi.dev/joke/Any?blacklistFlags=nsfw,racist,sexist,explicit&type=single') as r:
                res = await r.json()
                await interaction.response.send_message(res['joke'])

    @app_commands.command(name='8ball', description='get advice on anything')
    async def _8ball(self, interaction: discord.Interaction, question: str):
        responses = ['indeed', 'undoubtedly', 'no', 'dunno', 'indecisive']
        await interaction.response.send_message(f'> {question}\n:8ball: {random.choice(responses)}')

    @app_commands.command(name='rps', description='play rps for money')
    async def rps(self, interaction: discord.Interaction):
        await interaction.response.send_message('Send R for :rock:, send P for :scroll:, send S for :scissors:')

        def check(m):
            return m.content.lower() in ['r', 'p', 's'] and m.channel == interaction.channel and m.author == interaction.user

        message = await self.bot.wait_for('message', check=check, timeout=15)
        if message.content.lower() == 'r':
            player = 0
        elif message.content.lower() == 'p':
            player = 1
        elif message.content.lower() == 's':
            player = 2
        while True:
            computer = random.randint(0, 2)
            if self.scenarios[player][computer] == 'L':
                if random.randint(0, 2) == 0:
                    break
                else:
                    continue
            elif self.scenarios[player][computer] in ['W', 'D']:
                break
        outcome = self.scenarios[player][
            computer]  # Check the table for the outcome

        if outcome == 'W':
            await message.reply('You win! +50 beans')
            await self.bot.addcurrency(message.author, 50, 'wallet')
        elif outcome == 'L':
            await message.reply('I win!')
        elif outcome == 'D':
            await message.reply('Draw!')


async def setup(bot):
    await bot.add_cog(Fun(bot))
