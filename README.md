# kidney bot

## Don't want to host yourself? Add the bot [here](https://discord.com/oauth2/authorize?client_id=870379086487363605&permissions=8&scope=applications.commands%20bot)!

**Want to use my code in your bot?**
- That's great! Make sure to credit me, and according to GNU GPLv3, your license must also be GNU GPLv3

## Setup

kidney bot is set up to use the [uv package manager](https://docs.astral.sh/uv) for dependency management. Please follow their instructions to install it.

After installing uv, run the following command in the root directory of the project:

```bash
uv sync
```
This will install all the dependencies required for the bot to run.

### Linux

If you are running the bot on a Linux OS, you will need to install a couple packages

```bash
# Debian/Ubuntu
sudo apt install libffi-dev libnacl-dev python3-dev
# Fedora/CentOS/RHEL
sudo dnf install libffi-devel libsodium-devel python3-devel
# Arch Linux
sudo pacman -S libffi libsodium python
```

Then, either copy the `config.sample.json` file to `config.json` or run the setup script:

```bash
uv run setup.py
```

To start the bot, run:

```bash
uv run kidney-bot/main.py
```