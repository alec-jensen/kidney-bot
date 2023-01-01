# Custom permissions checks.
# Copyright (C) 2022  Alec Jensen
# Full license at LICENSE.md

import discord
from discord import app_commands
import json

with open('config.json', 'r') as f:
    config = json.load(f)


def is_owner():
    def predicate(interaction: discord.Interaction) -> bool:
        return str(interaction.user.id) == config.ownerid

    return app_commands.check(predicate)
