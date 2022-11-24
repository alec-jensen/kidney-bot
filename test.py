def initdb():
    global dataDB
    import motor.motor_asyncio
    client = motor.motor_asyncio.AsyncIOMotorClient(config['dbstring'])
    dataDB = client.data

