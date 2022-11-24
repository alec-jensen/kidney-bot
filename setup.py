# This file sets up all required files and the database.
# Copyright (C) 2022  Alec Jensen
# Full license at LICENSE.md

import os
import json
import motor.motor_asyncio
import requests
import sys

dbOnly = False

if '-db' in sys.argv:
    dbOnly = True

if not dbOnly:
    while True:
        token = input('Please paste the bot token EXACTLY as it appears in the developer portal.\n> ')
        bot = requests.get('https://discord.com/api/v10/users/@me', headers={'Authorization': f'Bot {token}'}).json()
        if bot.get('message') == '401: Unauthorized':
            print('It seems that bot doesn\'t exist.')
            continue
        else:
            _cont = input(f'You want to use bot "{bot["username"]}". Is that correct? (y/n)\n> ')
            if _cont.lower() == 'y':
                break
            elif _cont.lower() == 'n':
                continue

dbstring = input('Please paste the database access string EXACTLY as it appears in mongodb.\n> ')
ownerid = input('Please paste your Discord user ID.\n> ')

print('Generating config file...')
with open('config.json', 'w+') as f:
    json.dump({'token': token, 'dbstring': dbstring, 'ownerid': ownerid}, f)

if not os.path.exists('venv'):
    print('Please reinstall the venv correctly, as described in README.md')
    exit()

try:
    print('Checking if modules installed correctly...')
    import discord
    import aiohttp
    import pafy
    import psutil
    import motor
    import youtube_dl
    import nacl
except ImportError as error:
    print('Some or all required modules are missing. You may not have run this script in the venv, otherwise please '
          'install the required modules as described in README.md')
    print(error)
    exit()

print('Setup finished successfully. You may now start the bot.')
