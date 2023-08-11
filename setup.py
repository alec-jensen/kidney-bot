# This file sets up all required files and the database.
# Copyright (C) 2022  Alec Jensen
# Full license at LICENSE.md

import os
import json
import requests

if not os.path.exists('config.json'):
    config = {}

    while True:
        token = input('Please paste the bot token EXACTLY as it appears in the developer portal.\n> ')
        bot = requests.get('https://discord.com/api/v10/users/@me', headers={'Authorization': f'Bot {token}'}).json()
        if bot.get('message') == '401: Unauthorized':
            print('It seems that bot doesn\'t exist.')
            continue
        else:
            _cont = input(f'You want to use bot "{bot["username"]}". Is that correct? (y/n)\n> ')
            if _cont.lower() == 'y':
                config['token'] = token
                break
            elif _cont.lower() == 'n':
                continue

    dbstring = input('Please paste the database access string EXACTLY as it appears in mongodb.\n> ')
    config['dbstring'] = dbstring
    while True:
        ownerid = input('Please paste your Discord user ID.\n> ')
        user = requests.get(f'https://discord.com/api/v10/users/{ownerid}', headers={'Authorization': f'Bot {token}'}).json()
        if user.get('message') == '401: Unauthorized':
            print('It seems that user doesn\'t exist.')
            continue
        else:
            _cont = input(f'You are "{user["username"]}". Is that correct? (y/n)\n> ')
            if _cont.lower() == 'y':
                config['ownerid'] = int(ownerid)
                break
            elif _cont.lower() == 'n':
                continue

    while True:
        report_channel = input('Please paste the ID of the channel you want to use for reports.\n> ')
        channel = requests.get(f'https://discord.com/api/v10/channels/{report_channel}', headers={'Authorization': f'Bot {token}'}).json()
        if channel.get('message') == '401: Unauthorized':
            print('It seems that channel doesn\'t exist.')
            continue
        else:
            _cont = input(f'You want to use channel "{channel["name"]}". Is that correct? (y/n)\n> ')
            if _cont.lower() == 'y':
                config['report_channel'] = int(report_channel)
                break
            elif _cont.lower() == 'n':
                continue

    while True:
        error_channel = input('Please paste the ID of the channel you want to use for error reporting. Leave blank if you do not wish to report errors to a channel.\n> ')
        if error_channel == '':
            break
        channel = requests.get(f'https://discord.com/api/v10/channels/{error_channel}', headers={'Authorization': f'Bot {token}'}).json()
        if channel.get('message') == '401: Unauthorized':
            print('It seems that channel doesn\'t exist.')
            continue
        else:
            _cont = input(f'You want to use channel "{channel["name"]}". Is that correct? (y/n)\n> ')
            if _cont.lower() == 'y':
                config['error_channel'] = int(error_channel)
                break
            elif _cont.lower() == 'n':
                continue

    while True:
        user_count_channel = input('Please paste the ID of the channel you want to use for user count. Leave blank if you do not wish to have a user count channel.\n> ')
        if user_count_channel == '':
            break
        channel = requests.get(f'https://discord.com/api/v10/channels/{user_count_channel}', headers={'Authorization': f'Bot {token}'}).json()
        if channel.get('message') == '401: Unauthorized':
            print('It seems that channel doesn\'t exist.')
            continue
        else:
            _cont = input(f'You want to use channel "{channel["name"]}". Is that correct? (y/n)\n> ')
            if _cont.lower() == 'y':
                config['user_count_channel'] = int(user_count_channel)
                break
            elif _cont.lower() == 'n':
                continue

    perspective_api_key = input('Please paste your Perspective API key. If you don\'t want to use AI message filtering, leave this blank.\n> ')
    if perspective_api_key != '':
        config['perspective_api_key'] = perspective_api_key

    print('Generating config file...')
    with open('config.json', 'w+') as f:
        json.dump(config, f)
else:
    print('Config file already exists. Skipping config generation.')

print('Setup finished successfully. You may now start the bot.')
