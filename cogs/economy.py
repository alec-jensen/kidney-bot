import discord
from discord.ext import commands
import json
import random

""" currency data format:
{
    "userID": "",
    "wallet": "",
    "bank": "",
    "inventory": []
}
"""


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
            await dataDB.currency.update_one({'userID': str(user.id)}, {'$set': {'wallet': str(int(doc['wallet']) + value)}})
        elif location == 'bank':
            await dataDB.currency.update_one({'userID': str(user.id)}, {'$set': {'bank': str(int(doc['bank']) + value)}})
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


class Economy(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    async def initUser(self, user):
        await addcurrency(user, 0, 'wallet')

    @commands.Cog.listener()
    async def on_ready(self):
        print('Economy cog loaded.')

    @commands.command()
    @commands.is_owner()
    async def resetuser(self, ctx, user: discord.User):
        await dataDB.currency.delete_one({'userID': str(user.id)})
        await ctx.send('User removed successfully!')

    @commands.command(brief='Beg for beans', help='Imagine being that beanless lol. 30 second cooldown.')
    @commands.cooldown(1, 6, commands.BucketType.user)
    async def beg(self, ctx):
        amount = random.randint(0, 100)
        await addcurrency(ctx.author, amount, 'wallet')
        await ctx.message.reply(f'You gained {amount} from begging!')

    @commands.command(aliases=['bal'], brief='View your bean count',
                      help='Admire how many (or how few) beans you have.')
    async def balance(self, ctx, user: discord.User = None):
        if not user:
            user = ctx.author
        await self.initUser(user)
        doc = await dataDB.currency.find_one({'userID': str(user.id)})
        await ctx.reply(
            f"*{user.name}'s* balance:\n**Wallet: **{doc['wallet']} beans\n**Bank: **{doc['bank']} beans")

    @commands.command(aliases=['dep'], brief='Deposit beans',
                      help="Deposit beans in the bank so it doesn't get stolen.")
    async def deposit(self, ctx, amount):
        await self.initUser(ctx.author)
        doc = await dataDB.currency.find_one({'userID': str(ctx.author.id)})
        try:
            int(amount)
        except:
            if amount.lower() == 'all':
                amount = int(doc['wallet'])
            elif amount.lower() == 'half':
                amount = int(doc['wallet']) / 2
            else:
                await ctx.reply('Value must be a number')
                return
        if int(amount) <= int(doc['wallet']):
            await addcurrency(ctx.author, -int(amount), 'wallet')
            await addcurrency(ctx.author, int(amount), 'bank')
            await ctx.message.reply(f'Deposited {int(amount)} beans')
        else:
            await ctx.message.reply('You are trying to deposit more beans than you have!')

    @commands.command(aliases=['with'], brief='Withdraw beans', help='Withdraw beans so you can spend them.')
    async def withdraw(self, ctx, amount):
        await self.initUser(ctx.author)
        doc = await dataDB.currency.find_one({'userID': str(ctx.author.id)})
        try:
            int(amount)
        except:
            if amount.lower() == 'all':
                amount = int(doc['bank'])
            elif amount.lower() == 'half':
                amount = int(doc['bank']) / 2
            else:
                await ctx.message.reply('Value must be a number')
                return
        if int(amount) <= int(doc['bank']):
            await addcurrency(ctx.author, int(amount), 'wallet')
            await addcurrency(ctx.author, -int(amount), 'bank')
            await ctx.message.reply(f'Withdrew {amount} beans')
        else:
            await ctx.message.reply('You are trying to withdraw more beans than you have!')

    @commands.command(brief='Rob someone',
                      help='Rob someone of their beans and make then very mad. 30 second cooldown.')
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def rob(self, ctx, user: discord.User):
        await self.initUser(ctx.author)
        targetDoc = await dataDB.currency.find_one({'userID': str(user.id)})
        if int(targetDoc['wallet']) <= 11:
            await ctx.reply('They have no beans!')
        else:
            doc = await dataDB.currency.find_one({'userID': str(ctx.author.id)})
            if int(doc['wallet']) <= 50:
                await ctx.reply('You don\'t have enough money!')
                return
            amount = random.randint(0, int(int(doc['wallet']) / 6))
            if amount < 2:
                await ctx.reply('You were caught! You pay 50 beans in fines.')
                await addcurrency(ctx.author, -50, 'wallet')
                return
            await addcurrency(user, -amount, 'wallet')
            await addcurrency(ctx.author, amount, 'wallet')
            await ctx.message.reply(f"Stole {amount} beans from {user.mention}")


async def setup(bot):
    initdb()
    await bot.add_cog(Economy(bot))
