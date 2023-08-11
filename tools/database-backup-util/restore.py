# This utility can be used to restore the database from a backup. 
# Copyright (C) 2022  Alec Jensen
# Full license at LICENSE.md

"""
make sure to EMPTY YOUR DATABASE before restoring from a backup.
"""

import os
import argparse
import pymongo
from pymongo import MongoClient
import bson
from bson import json_util 
import json
import sys

parser = argparse.ArgumentParser(prog='DatabaseRestoreTool', description='Restore your MongoDB database from a backup!', epilog='Written by Alec Jensen')

parser.add_argument('backup_name')
parser.add_argument('database_conn_string')
parser.add_argument('-c', '--collection')

args = parser.parse_args()

dir = os.path.realpath(os.path.dirname(__file__))

if not os.path.exists(f'{dir}/backup/{args.backup_name}'):
    print('ERROR: Backup doesn\'t exist! check filename.')
    sys.exit()
    
directory = f'{dir}/backup/{args.backup_name}'

client = MongoClient(args.database_conn_string)
db = client.data

if args.collection is None:
    for collection in os.listdir(directory):
        print(f'restoring {collection}')
        f = os.path.join(directory, collection)
        if os.path.isdir(f):
            for document in os.listdir(f):
                doc = os.path.join(directory, collection, document)
                with open(doc, 'r') as f:
                    loadedDoc = json.loads(json_util.loads(f.read()))
                    loadedDoc['_id'] = bson.ObjectId(loadedDoc['_id']['$oid'])
                    try:
                        db[collection].insert_one(loadedDoc)
                        print(f'\trestoring {document}')
                    except pymongo.errors.DuplicateKeyError:
                        print('\tskipping duplicate')

else:
    collection = args.collection
    print(f'restoring {collection}')
    f = os.path.join(directory, collection)
    if os.path.isdir(f):
        for document in os.listdir(f):
            doc = os.path.join(directory, collection, document)
            print(f'\trestoring {document}')
            with open(doc, 'r') as f:
                db[collection].insert_one(json_util.loads(f.read()))