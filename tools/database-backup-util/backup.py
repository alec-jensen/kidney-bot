# This utility can be used to backup the database to the local machine.
# Copyright (C) 2022  Alec Jensen
# Full license at LICENSE.md

"""
it is recommended to set up this to run as a cron job at least daily.
add a https://ntfy.sh/ topic url to post-alert-url.txt to get a notification of successful backups and unsuccessful backups
"""

from pymongo import MongoClient
from bson import json_util 
import json
import requests
import logging
import traceback
import datetime
import os

ALERT_URL = None

now = datetime.datetime.now()
fileNameFormat = f'{now.year}_{now.month}_{now.day}_{now.hour}-{now.minute}-{now.second}'

try:
    dir = os.path.realpath(os.path.dirname(__file__))
    if not os.path.exists(f'{dir}/backup'):
        os.makedirs(f'{dir}/backup')
    if not os.path.exists(f'{dir}/logs'):
        os.makedirs(f'{dir}/logs')
    with open(f'{dir}/post-alert-url.txt', 'r') as f:
        ALERT_URL = f.read()

    logFormatter = logging.Formatter("[%(asctime)s] [%(levelname)8s] --- %(message)s (%(name)s - %(filename)s:%(lineno)s)", '%H:%M:%S')
    rootLogger = logging.getLogger()
    rootLogger.setLevel(logging.INFO)

    fileHandler = logging.FileHandler(f'{dir}/logs/{fileNameFormat}.txt')
    fileHandler.setFormatter(logFormatter)
    rootLogger.addHandler(fileHandler)

    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    rootLogger.addHandler(consoleHandler)

    logging.info('Starting database backup.')
    if not os.path.exists(f'{dir}/backup/{fileNameFormat}'):
        os.makedirs(f'{dir}/backup/{fileNameFormat}')
    with open(f'{os.path.abspath(os.path.join(os.path.join(dir, os.pardir), os.pardir))}/config.json', 'r') as f:
        client = MongoClient(json.load(f)['dbstring'])
    db = client.data
    for coll_name in db.list_collection_names():
        if not os.path.exists(f'{dir}/backup/{fileNameFormat}/{coll_name}'):
            os.makedirs(f'{dir}/backup/{fileNameFormat}/{coll_name}')
        logging.info(f"collection:{coll_name}")
        for r in db[coll_name].find({}):
            with open(f'{dir}/backup/{fileNameFormat}/{coll_name}/{r["_id"]}.bson', 'w+') as f:
                json.dump(json_util.dumps(r), f)

    logging.info(f'Database backed up successfully! {os.path.join(dir, "backup", fileNameFormat)}')
    if ALERT_URL is not None and ALERT_URL != "":
        try:
            requests.post(ALERT_URL, data=f'DATABASE BACKUP SUCCESS. Log saved as {fileNameFormat}.txt!')
        except:
            pass

except Exception as e:
    tb = traceback.format_exception(type(e), e, e.__traceback__)
    formattedTB = '"'
    for i in tb:
        if i == tb[-1]:
            formattedTB = f'{formattedTB}{i}"'
        else:
            formattedTB = f'{formattedTB}{i}'
    logging.error(formattedTB)
    if ALERT_URL is not None and ALERT_URL != "":
        try:
            requests.post(ALERT_URL, data=f'DATABASE BACKUP FAILED. Log saved as {fileNameFormat}.txt!')
        except:
            pass