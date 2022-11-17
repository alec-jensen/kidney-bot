# kidney bot

## Don't want to host yourself? Add the bot [here](https://discord.com/oauth2/authorize?client_id=870379086487363605&permissions=8&scope=applications.commands%20bot)!

**Want to use my code in your bot?**
- That's great! Make sure to credit me, and according to GNU GPLv3, your license must also be GNU GPLv3

Want to host the bot yourself? Follow these instructions:

- Create a bot through the [discord developer portal](https://discord.com/developers/applications)
- Create a [MongoDB Database](https://www.mongodb.com/)
- Create a cluster in the database. It can have any name.
- Create a virtual environment `python3 -m venv venv`
- Enter the virtual environment Linux/MacOS: `source venv/bin.active` Windows: `.\venv\Scripts\activate`
- Install the required packages `python3 -m pip install -r requirements.txt`
- Run the setup `python3 setup.py` Make sure to run this in the venv, and provide all requested information **EXACTLY**

Start the bot with `python3 main.py`

todo: setup.py file to automatically ask for these then setup database.
