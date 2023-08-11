# Config class for kidney-bot
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import json

class Config:
    def __init__(self):
        with open('config.json', 'r') as f:
            self.conf_json = json.load(f)
        try:
            self.token: str = self.conf_json['token']
            self.dbstring: str = self.conf_json['dbstring']
            self.owner_id: int = int(self.conf_json['ownerid'])
            self.report_channel: int = int(self.conf_json['report_channel'])
            self.perspective_api_key: str | None = self.conf_json.get('perspective_api_key')
            self.error_channel: int | None = int(self.conf_json.get('error_channel')) if self.conf_json.get('error_channel') else None
            self.user_count_channel: int | None = int(self.conf_json.get('user_count_channel')) if self.conf_json.get('user_count_channel') else None
        except KeyError as e:
            raise KeyError(f'Config file is missing a key: {e}')
