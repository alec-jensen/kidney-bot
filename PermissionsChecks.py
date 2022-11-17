"""
Custom permissions check coded by Alec Jensen
"""

import discord
from discord import app_commands
import json

with open('config.json', 'r') as f:
    config = json.load(f)

def is_owner():
    def predicate(interaction: discord.Interaction) -> bool:
        return str(interaction.user.id) in config['ownerid']
    return app_commands.check(predicate)
