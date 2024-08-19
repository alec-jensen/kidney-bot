# This cog creates all economy based commands
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import discord
from discord.ext import commands
from discord import app_commands
import random
import logging
from typing import Literal, Optional
import asyncio

from utils.database import Database
from utils.kidney_bot import KidneyBot
from utils.checks import is_bot_owner
import utils.types as types

class Item:
    def __init__(self, id: str, name: str, price: int, description: str, one_time: bool,
                 callback: Optional[types.AsyncFunction] = None, max_quantity: int | float = float('inf')):
        self.id = id
        self.name = name
        self.price = price
        self.description = description
        self.one_time = one_time
        self.usable = True
        self.max_quantity = max_quantity

        if callback is None:
            self.usable = False
            async def default_callback(interaction: discord.Interaction):
                await interaction.followup.send('This item is not usable.')
            self.callback = default_callback
        else:
            self.callback = callback

    async def use(self, interaction: discord.Interaction):
        await self.callback(interaction)

items: list[Item] = []


async def bean_bomb(interaction: discord.Interaction):
    amount = random.randint(0, 100)
    users = []
    channel = interaction.channel
    async for message in channel.history(limit=100):
        if message.author.id in users:
            continue

        if message.author.bot:
            continue

        if message.created_at.timestamp() < interaction.created_at.timestamp() - 60:
            continue

        users.append(message.author.id)

        user = UserProfile(interaction.client, interaction.client.database, message.author)
        await user.async_init()
        await user.add_currency(amount, 'wallet')

    await interaction.followup.send(f'Everyone in the channel got {amount} beans!')

items.append(Item('bean_bomb', 'Bean Bomb', 100,
                 'Explode your beans and give everyone in the channel some!', True, bean_bomb))

items.append(Item('padlock', 'Padlock', 100,
                 'Lock your wallet to prevent robbers!', True))

items.append(Item('bolt_cutters', 'Bolt Cutters', 250,
                 'Cut off a padlock to rob someone!', True))

async def cookie(interaction: discord.Interaction):
    await interaction.followup.send('You ate a cookie.')

items.append(Item('cookie', 'Cookie', 10, 'A delicious cookie.', True, cookie))

items.append(Item('can_of_beans', 'Can of Beans', 50, 'A can of beans.', False))

items.append(Item('metal_pipe', 'Metal Pipe', 100, 'A metal pipe.', False))

class PhoneView(discord.ui.View):
    def __init__(self, interaction: discord.Interaction):
        super().__init__()
        self.interaction = interaction

    @discord.ui.button(label='Order a pizza', style=discord.ButtonStyle.secondary)
    async def pizza(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        profile = UserProfile(interaction.client, interaction.client.database, interaction.user)
        await profile.async_init()
        if await profile.wallet() < 20:
            await self.interaction.followup.send('You don\'t have enough beans!', ephemeral=True)
            return
        
        await profile.add_currency(-20, 'wallet')

        await profile.add_item(next(i for i in items if i.id == 'pizza'))

        await self.interaction.followup.send('You ordered a pizza for 20 beans!')

    @discord.ui.button(label='Prank call the developer', style=discord.ButtonStyle.secondary)
    async def prank_call(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.interaction.followup.send(':telephone: Calling the developer...')
        await asyncio.sleep(random.randint(5, 20) / 10)
        pranks = ["Your refrigerator is running, you better go catch it!", "Your bot is broken, lol", "You're a nerd",
                  "I'm calling about your car's extended warranty", "I'm calling from the IRS, you owe us money"]
        await self.interaction.channel.send(f"You: {random.choice(pranks)}")
        await asyncio.sleep(random.randint(5, 20) / 10)
        await self.interaction.channel.send('Developer: ...')
        await asyncio.sleep(random.randint(5, 20) / 10)
        await self.interaction.channel.send('Developer: Stop calling me!')
        await self.interaction.channel.send('The developer hung up on you.')

async def phone(interaction: discord.Interaction):
    view = PhoneView(interaction)
    await interaction.followup.send('What do you want to do with your phone?', view=view)

items.append(Item('phone', 'Phone', 100, 'A phone.', False, callback=phone, max_quantity=1))

async def pizza(interaction: discord.Interaction):
    await interaction.followup.send('You ate a pizza.')

items.append(Item('pizza', 'Pizza', 20, 'A pizza.', True, pizza))

ItemIDsLiteral = Literal['bean_bomb - 100', 'padlock - 100', 'bolt_cutters - 250', 'cookie - 10', 'can_of_beans - 50', 'metal_pipe - 100',
                        'phone - 100', 'pizza - 20']

items_per_page = 5
num_pages = (len(items) + items_per_page - 1) // items_per_page

class PageDropdown(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=str(i+1), value=str(i+1)) for i in range(num_pages)]
        super().__init__(placeholder='Select a page...', min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        view: Shop = self.view
        view.page = int(self.values[0]) - 1
        await view.update(interaction.message)
        await interaction.response.defer()

class Shop(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.page = 0
        self.add_item(PageDropdown())

    @discord.ui.button(label='Back', style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page == 0:
            return
        self.page -= 1
        await self.update(interaction.message)
        await interaction.response.defer()

    @discord.ui.button(label='Next', style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page == num_pages - 1:
            return
        self.page += 1
        await self.update(interaction.message)
        await interaction.response.defer()

    async def update(self, message: discord.Message):
        next_button = discord.utils.get(self.children, label='Next')
        back_button = discord.utils.get(self.children, label='Back')
        if self.page == 0:
            back_button.disabled = True
        else:
            back_button.disabled = False
        if self.page == num_pages - 1:
            next_button.disabled = True
        else:
            next_button.disabled = False

        embed = discord.Embed(title="Shop", color=discord.Color.green())
        for i in range(self.page * items_per_page, (self.page + 1) * items_per_page):
            if i >= len(items):
                break
            item = items[i]
            embed.add_field(name=f"{item.name} - {item.price} beans", value=item.description, inline=False)
        embed.set_footer(text=f"Page {self.page + 1}/{num_pages}")
        await message.edit(embed=embed, view=self)


class UserProfile:
    def __init__(self, bot: KidneyBot, database: Database, user: discord.User | discord.Member):
        self.bot: KidneyBot = bot
        self.database: Database = database
        self.user: discord.User | discord.Member = user

    async def async_init(self):
        await self.bot.add_currency(self.user, 0, 'wallet')

    async def wallet(self) -> int:
        doc = await self.database.currency.find_one({'userID': str(self.user.id)})
        return int(doc['wallet'])

    async def bank(self) -> int:
        doc = await self.database.currency.find_one({'userID': str(self.user.id)})
        return int(doc['bank'])

    async def inventory(self) -> dict:
        doc = await self.database.currency.find_one({'userID': str(self.user.id)})
        if type(doc.get('inventory')) is not dict:
            doc['inventory'] = {}
        return doc['inventory']
    
    async def add_item(self, item: Item):
        doc = await self.database.currency.find_one({'userID': str(self.user.id)})
        if type(doc.get('inventory')) is not dict:
            doc['inventory'] = {}
        count = doc['inventory'].get(item.id, 0)
        count += 1
        doc['inventory'][item.id] = count
        await self.database.currency.update_one({'userID': str(self.user.id)}, {'$set': {'inventory': doc['inventory']}})

    async def remove_item(self, id: str, amount: int = 1):
        doc = await self.database.currency.find_one({'userID': str(self.user.id)})
        count = doc['inventory'].get(id, 0)
        count -= amount
        if count < 0:
            count = 0
        doc['inventory'][id] = count
        await self.database.currency.update_one({'userID': str(self.user.id)}, {'$set': {'inventory': doc['inventory']}})

    async def doc(self):
        return await self.database.currency.find_one({'userID': str(self.user.id)})

    async def add_currency(self, amount: int, location: str):
        location = location.lower()
        if location not in ['wallet', 'bank']:
            raise ValueError(
                f"Parameter \"location\" must be 'wallet' or 'bank' got: {location}")
        await self.bot.add_currency(self.user, amount, location)


class Economy(commands.Cog):

    def __init__(self, bot):
        self.bot: KidneyBot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info('Economy cog loaded.')

    @commands.command()
    @is_bot_owner()
    async def resetuser(self, ctx, user: discord.User):
        await self.bot.database.currency.delete_one({'userID': str(user.id)})
        await ctx.send('User removed successfully!')

    @commands.command()
    @is_bot_owner()
    async def addmoney(self, ctx, user: discord.User, amount: int):
        await self.bot.add_currency(user, amount, 'wallet')

    @app_commands.command(name="beg", description='Imagine being that beanless lol. 30 second cooldown.')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.checks.cooldown(1, 6, key=lambda i: i.user.id)
    async def beg(self, interaction: discord.Interaction):
        await interaction.response.defer()
        amount = random.randint(0, 100)
        await self.bot.add_currency(interaction.user, amount, 'wallet')
        await interaction.followup.send(f'You gained {amount} from begging!')

    @app_commands.command(name="balance", description='View your bean count')
    @app_commands.allowed_installs(guilds=True, users=True)
    async def balance(self, interaction: discord.Interaction, user: types.OptAnyUser = None):
        await interaction.response.defer()
        if not user:
            user = interaction.user
        profile = UserProfile(self.bot, self.bot.database, user)
        await profile.async_init()

        embed = discord.Embed(title=f"{user.display_name}'s balance", color=0x00ff00)
        embed.add_field(name="Wallet", value=f"{await profile.wallet()} beans", inline=False)
        embed.add_field(name="Bank", value=f"{await profile.bank()} beans", inline=False)
        embed.set_footer(text=user.name, icon_url=user.display_avatar.url)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="deposit", description='Deposit beans')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(amount="Numerical value, 'all', or 'half'")
    async def deposit(self, interaction: discord.Interaction, amount: str):
        await interaction.response.defer()
        profile = UserProfile(self.bot, self.bot.database, interaction.user)
        await profile.async_init()
        try:
            int(amount)
        except:
            if amount.lower() == 'all':
                amount = int(await profile.wallet())
            elif amount.lower() == 'half':
                amount = int(await profile.wallet()) // 2
            else:
                await interaction.followup.send('Value must be a number, "all", or "half"', ephemeral=True)
                return
        if int(amount) <= int(await profile.wallet()):
            await profile.add_currency(-int(amount), 'wallet')
            await profile.add_currency(int(amount), 'bank')
            await interaction.followup.send(f'Deposited {int(amount)} beans')
        else:
            await interaction.followup.send('You are trying to deposit more beans than you have!',
                                                    ephemeral=True)

    @app_commands.command(name="withdraw", description="Withdraw beans")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(amount="Numerical value, 'all', or 'half'")
    async def withdraw(self, interaction: discord.Interaction, amount: str):
        await interaction.response.defer()
        profile = UserProfile(self.bot, self.bot.database, interaction.user)
        await profile.async_init()
        try:
            int(amount)
        except:
            if amount.lower() == 'all':
                amount = int(await profile.bank())
            elif amount.lower() == 'half':
                amount = int(await profile.bank()) // 2
            else:
                await interaction.followup.send('Value must be a number, "all", or "half"', ephemeral=True)
                return
        if int(amount) <= int(await profile.bank()):
            await profile.add_currency(int(amount), 'wallet')
            await profile.add_currency(-int(amount), 'bank')
            await interaction.followup.send(content=f'Withdrew {amount} beans')
        else:
            await interaction.followup.send('You are trying to withdraw more beans than you have!',
                                                    ephemeral=True)

    @app_commands.command(name='rob',
                          description='Rob someone of their beans and make them very mad. 30 second cooldown.')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.checks.cooldown(1, 30, key=lambda i: i.user.id)
    async def rob(self, interaction: discord.Interaction, target: discord.User):
        USED_BOLT_CUTTERS = False
        await interaction.response.defer()
        profile = UserProfile(self.bot, self.bot.database, interaction.user)
        await profile.async_init()

        target_profile = UserProfile(self.bot, self.bot.database, target)
        await target_profile.async_init()

        if int(await target_profile.wallet()) <= 11:
            await interaction.followup.send('They have no beans!', ephemeral=True)
        else:
            if interaction.user.id == target.id:
                amount = random.randint(0, int(await profile.wallet() // 6))
                await profile.add_currency(-amount, 'wallet')
                await interaction.followup.send(f"You tried to rob yourself and lost {amount} beans. Good job.")
                return
            if int(await profile.wallet()) <= 50:
                await interaction.followup.send('You don\'t have enough money in your wallet!', ephemeral=True)
                return
            user_inventory = await profile.inventory()
            target_inventory = await target_profile.inventory()
            if 'padlock' in target_inventory:
                if 'bolt_cutters' not in user_inventory:
                    await interaction.followup.send('They have a padlock on their wallet! You were caught, and lost 50 beans!', ephemeral=True)
                    await profile.add_currency(-50, 'wallet')
                    await target_profile.remove_item('padlock')
                    try:
                        await target.send(f"{interaction.user.name} tried to rob you, but you had a padlock on your wallet! They lost 50 beans, and your padlock broke.")
                    except:
                        pass
                    return
                else:
                    await target_profile.remove_item('padlock')
                    await profile.remove_item('bolt_cutters')
                    USED_BOLT_CUTTERS = True
            amount = random.randint(0, int(await target_profile.wallet() // 6))
            if amount < 2:
                await interaction.followup.send('You were caught! You pay 50 beans in fines.')
                await profile.add_currency(-50, 'wallet')
                return
            await target_profile.add_currency(-amount, 'wallet')
            await profile.add_currency(amount, 'wallet')

            if USED_BOLT_CUTTERS:
                await interaction.followup.send(f"{target.mention} had a padlock on their wallet, \
but you used bolt cutters to break it! Unfortunatly, \
your bolt cutters broke in the process. Fortunately, \
you got {amount} beans!")
            else:
                await interaction.followup.send(f"Stole {amount} beans from {target.mention}")

    @app_commands.command(name='shop', description='Buy items from the shop')
    @app_commands.allowed_installs(guilds=True, users=True)
    async def shop(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view = Shop()
        embed = discord.Embed(title="Shop", color=discord.Color.green())
        await interaction.followup.send(embed=embed, view=view)
        await view.update(await interaction.original_response())

    @app_commands.command(name='buy', description='Buy an item from the shop')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(item="The item you want to buy")
    async def buy(self, interaction: discord.Interaction, item: ItemIDsLiteral):
        await interaction.response.defer()
        profile = UserProfile(self.bot, self.bot.database, interaction.user)
        await profile.async_init()
        item_obj: Item = next(i for i in items if i.id == item.split(' ')[0])
        inv = await profile.inventory()
        if item_obj.id in inv and inv[item_obj.id] >= item_obj.max_quantity:
            await interaction.followup.send('You have reached the maximum quantity of this item!', ephemeral=True)
            return
        if int(await profile.wallet()) < item_obj.price:
            await interaction.followup.send('You don\'t have enough beans!', ephemeral=True)
            return
        await profile.add_currency(-item_obj.price, 'wallet')
        await profile.add_item(item_obj)

        await interaction.followup.send(f'You bought a {item_obj.name} for {item_obj.price} beans!')

    @app_commands.command(name='use', description='Use an item from your inventory')
    @app_commands.describe(item="The item you want to use")
    async def use(self, interaction: discord.Interaction, item: str):
        await interaction.response.defer()
        item = item.split(' ')[0]
        profile = UserProfile(self.bot, self.bot.database, interaction.user)
        await profile.async_init()
        item_obj: Item = next(i for i in items if i.id == item)
        inventory = await profile.inventory()
        if item not in inventory or inventory[item] == 0:
            await interaction.followup.send('You don\'t have that item!', ephemeral=True)
            return
        await item_obj.use(interaction)
        if item_obj.one_time:
            inventory[item] -= 1
            doc = await profile.doc()
            doc['inventory'] = inventory
            await self.bot.database.currency.update_one({'userID': str(interaction.user.id)}, {'$set': doc})

    @use.autocomplete('item')
    async def item_autocomplete(self, interaction: discord.Interaction, current: str):
        items = []
        profile = UserProfile(self.bot, self.bot.database, interaction.user)
        await profile.async_init()
        inventory = await profile.inventory()
        for item in inventory:
            if inventory[item] == 0:
                continue
            items.append(f"{item} x{inventory[item]}")
        return [app_commands.Choice(name=i, value=i) for i in items]

    @app_commands.command(name='inventory', description='View your inventory')
    @app_commands.allowed_installs(guilds=True, users=True)
    async def inventory(self, interaction: discord.Interaction):
        await interaction.response.defer()
        profile = UserProfile(self.bot, self.bot.database, interaction.user)
        await profile.async_init()
        inventory = await profile.inventory()
        embed = discord.Embed(title=f"{interaction.user.display_name}'s inventory", color=0x00ff00)
        i = 0
        for item in inventory:
            if inventory[item] == 0:
                continue
            i += 1
            item_obj = next(i for i in items if i.id == item)
            embed.add_field(name=f"{item_obj.name} x{inventory[item]}", value=item_obj.description, inline=False)
        if i == 0:
            embed.add_field(name="Empty", value="You have no items in your inventory", inline=False)

        await interaction.followup.send(embed=embed)

    @app_commands.command(name='pay', description='Pay someone beans')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(amount="Numerical value")
    async def pay(self, interaction: discord.Interaction, target: discord.User, amount: int):
        await interaction.response.defer()
        profile = UserProfile(self.bot, self.bot.database, interaction.user)
        await profile.async_init()
        target_profile = UserProfile(self.bot, self.bot.database, target)
        await target_profile.async_init()
        if int(await profile.wallet()) < amount:
            await interaction.followup.send('You don\'t have enough beans!', ephemeral=True)
            return
        await profile.add_currency(-amount, 'wallet')
        await target_profile.add_currency(amount, 'wallet')
        await interaction.followup.send(f'You paid {amount} beans to {target.mention}')


async def setup(bot):
    await bot.add_cog(Economy(bot))
