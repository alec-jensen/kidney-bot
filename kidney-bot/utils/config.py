# Config class for kidney-bot
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import json
import logging
import os
import shutil
import sys
import yaml

from utils.database import convert_except_none


class Config:
    def __init__(self):
        if not os.path.exists('config.json'):
            logging.critical(
                'Config file does not exist. Create sample? (y/n)')
            if input("> ") == 'y':
                shutil.copyfile('config.sample.json', 'config.json')
                logging.info(
                    'Sample config created. Please edit it. Come back when you are done.')
                input('Press enter to continue.')
                logging.info('Continuing bot startup.')
            else:
                logging.info('Exiting.')
                sys.exit(0)

        self.load()

    def load(self) -> None:
        with open('config.json', 'r') as f:
            self.conf_json: dict = json.load(f)

        try:
            self.token: str = self.conf_json['token']
            self.dbstring: str = self.conf_json['dbstring']

            if type(self.conf_json.get('ownerid')) == list:
                self.owner_id = None
                self.owner_ids = set([convert_except_none(
                    i, int) for i in self.conf_json.get('ownerid', []) if i is not None])
            else:
                self.owner_id = convert_except_none(
                    self.conf_json.get('ownerid'), int)
                self.owner_ids = None

            self.report_channel: int | None = convert_except_none(
                self.conf_json.get('report_channel'), int, error=False)
            if self.report_channel is None:
                logging.warning(
                    'No report channel configured, user reports will be disabled.')

            self.perspective_api_key: str | None = self.conf_json.get(
                'perspective_api_key')
            if self.perspective_api_key == '':
                self.perspective_api_key = None

            if self.perspective_api_key is None:
                logging.warning(
                    'No Perspective API key configured, perspective will be disabled.')

            self.error_channel: int | None = convert_except_none(
                self.conf_json.get('error_channel'), int, error=False)
            if self.error_channel is None:
                logging.warning(
                    'No error channel configured, errors will only be logged to console.')
                
            self.user_count_channel_id: int | None = convert_except_none(
                self.conf_json.get('user_count_channel'), int, error=False)

            self.prefix: str = self.conf_json.get('prefix', 'kb.')
            if self.prefix == '':
                self.prefix = 'kb.'

            self.langfile: str = self.conf_json.get(
                'langfile', 'lang/en_us.yml')
            if self.langfile == '':
                self.langfile = 'lang/en_us.yml'

            if not os.path.exists(self.langfile):
                raise FileNotFoundError(
                    f'Language file {self.langfile} does not exist.')

            self.heartbeat_url: str = self.conf_json.get('heartbeat_url', None)
            if self.heartbeat_url == '':
                self.heartbeat_url = None

            with open(self.langfile, 'r') as f:
                self.lang = yaml.safe_load(f)

        except KeyError as e:
            raise KeyError(f'Config file is missing a required option: {e}')

    def reload(self) -> None:
        with open('config.json', 'r') as f:
            self.conf_json = json.load(f)

        if self.token != self.conf_json['token']:
            raise ValueError('Token changed, please restart kidney-bot.')

        if self.dbstring != self.conf_json['dbstring']:
            raise ValueError(
                'Database string changed, please restart kidney-bot.')

        self.load()
