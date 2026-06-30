from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

import discord

AnyUser = discord.Member | discord.User
OptAnyUser = AnyUser | None

T = TypeVar("T")
P = ParamSpec("P")
AsyncFunction = Callable[P, Awaitable[T]] | Callable
