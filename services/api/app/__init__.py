"""Web dashboard backend for kidney-bot.

Reuses `utils.database` from the bot's own source tree directly (no
duplication of schema/collection logic) — this package never imports
anything from `cogs/` or connects to Discord's gateway.
"""

import pathlib
import sys

_BOT_SRC = pathlib.Path(__file__).resolve().parents[3] / "kidney-bot"
if str(_BOT_SRC) not in sys.path:
    sys.path.insert(0, str(_BOT_SRC))
