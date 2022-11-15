# kidney bot

## Don't want to host yourself? Add the bot [here](https://discord.com/oauth2/authorize?client_id=870379086487363605&permissions=8&scope=applications.commands%20bot)!

**Want to use my code in your bot?**
- That's great! Make sure to credit me, and according to GNU GPLv3, your license must also be GNU GPLv3

Want to host the bot yourself? Follow these instructions:

- Create a bot through the [discord developer portal](https://discord.com/developers/applications)

- Create a file named `token.txt` in the root directory. Place the token in this file.

- Create a [MongoDB Database](https://www.mongodb.com/)

- Create a file called `dbstring.txt` in the root directory. Place the server access string here.

- Structure your database as follows:

  - Cluster0
    - data
      - bans
      - currency
      - prefixes
      - serverbans
    
![image](https://user-images.githubusercontent.com/59067840/201986834-dc977beb-d38c-4aac-9c34-5200aff0d6dc.png)

start the bot with `python3 main.py`

todo: setup.py file to automatically ask for these then setup database.
