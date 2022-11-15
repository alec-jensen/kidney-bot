# This cog creates all "fun" commands
# Copyright (C) 2022  Alec Jensen
# Full license at LICENSE.md

import discord
from discord.ext import commands
import requests
import asyncio
import random


def initdb():
    global dataDB
    import motor.motor_asyncio
    with open('dbstring.txt') as f:
        string = f.readlines()
    client = motor.motor_asyncio.AsyncIOMotorClient(string)
    dataDB = client.data


async def addcurrency(user: discord.User, value: int, location: str):
    n = await dataDB.currency.count_documents({"userID": str(user.id)})
    if n == 1:
        doc = await dataDB.currency.find_one({"userID": str(user.id)})
        if location == 'wallet':
            await dataDB.currency.update_one({'userID': str(userID)}, {'$set': {'wallet': str(int(doc['wallet']) + value)}})
        elif location == 'bank':
            await dataDB.currency.update_one({'userID': str(userID)}, {'$set': {'bank': str(int(doc['bank']) + value)}})
    else:
        wallet, bank = (0, 0)
        if location == 'wallet':
            wallet = value
        elif location == 'bank':
            bank = value
        await dataDB.currency.insert_one({
            "userID": str(user.id),
            "wallet": str(wallet),
            "bank": str(bank),
            "inventory": []
        })


class Fun(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print('Fun cog loaded.')

    @commands.command(brief='Get a yomama joke', help='Get a yomama joke hot off the press.')
    async def yomama(self, ctx):
        result = requests.get('https://api.yomomma.info/').json()
        await ctx.message.reply(result["joke"])

    @commands.command(brief='Get a dad joke', help='Get a dad joke straight from certified dads.')
    async def dadjoke(self, ctx):
        result = requests.get('https://icanhazdadjoke.com/', headers={"Accept": "application/json"}).json()
        await ctx.message.reply(result["joke"])

    @commands.command(brief='Get a dog pic', help='Get a random dog pic. Who doesnt love dogs?')
    async def dog(self, ctx):
        result = requests.get('https://dog.ceo/api/breeds/image/random').json()
        await ctx.message.reply(result["message"])

    @commands.command(brief='Get a duck pic',
                      help='Get a random quacker image and participate in a minute amount of tomfoolery.')
    async def duck(self, ctx):
        result = requests.get('https://random-d.uk/api/random').json()
        await ctx.message.reply(result["url"])

    @commands.command(brief='Cat pic', help='I hate cats.')
    async def cat(self, ctx):
        result = requests.get('https://aws.random.cat/meow').json()
        await ctx.message.reply(result["file"])

    @commands.command(brief='Get roasted', help="Have the bot roast you? I don't know why you would want that...")
    async def roast(self, ctx):
        await ctx.message.reply("This command again no longer works.")
        """result = requests.get('http://insultgenerator.apiblueprint.org/insults').json()
        await ctx.message.reply(result['insults']['insult_name'].replace('<name', ctx.author.name))"""

    @commands.command(brief=':rofl:',
                      help=':smile: :face_with_symbols_over_mouth: :cold_face: :kissing_smiling_eyes: :imp: :point_right: :call_me: :muscle: :leg: :persevere:')
    async def meme(self, ctx):
        result = requests.get('https://meme-api.herokuapp.com/gimme').json()
        await ctx.message.reply(result["url"])

    @commands.command(brief='its a joke..', help='its just a joke...... why do you need help???')
    async def joke(self, ctx):
        result = requests.get('https://v2.jokeapi.dev/joke/Any').json()
        if result['type'] == 'twopart':
            await ctx.message.reply(result["setup"])
            async with ctx.typing():
                await asyncio.sleep(1)
            await ctx.send(result['delivery'])
        elif result['type'] == 'single':
            await ctx.message.reply(result['joke'])

    @commands.command(brief='magic', help='get advice on anything', name='8ball')
    async def _8ball(self, ctx):
        responses = ['indeed', 'undoubtedly', 'no', 'dunno', 'indecisive']
        await ctx.reply(f':8ball: {random.choice(responses)}')

    @commands.command(brief='play rps for money', help='play rock paper scissors against me', aliases=['rps'])
    async def rockpaperscissors(self, ctx):
        await ctx.reply('Send R for :rock:, send P for :scroll:, send S for :scissors:')
        choices = ['R', 'P', 'S']
        choice = random.choice(choices)

        def check(m):
            return m.content.lower() in ['r', 'p', 's'] and m.channel == ctx.channel and m.author == ctx.author

        message = await self.bot.wait_for('message', check=check, timeout=15)
        if message.content.lower() == 'r':
            if choice == 'R':
                await message.reply(f'Tie!')
            elif choice == 'P':
                await message.reply('Loss!')
            elif choice == 'S':
                await message.reply('Win!')
                addcurrency(ctx.author, 50, 'wallet')
        if message.content.lower() == 'p':
            if choice == 'R':
                await message.reply('Win!')
                addcurrency(ctx.author, 50, 'wallet')
            elif choice == 'P':
                await message.reply('Tie!')
            elif choice == 'S':
                await message.reply('Loss!')
        if message.content.lower() == 's':
            if choice == 'R':
                await message.reply('Loss!')
            elif choice == 'P':
                await message.reply('Win!')
                addcurrency(ctx.author, 50, 'wallet')
            elif choice == 'S':
                await message.reply('Tie!')


async def setup(bot):
    initdb()
    await bot.add_cog(Fun(bot))
