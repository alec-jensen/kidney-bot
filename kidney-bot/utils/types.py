import discord
from typing import Union, Optional, TypeVar, ParamSpec, Awaitable, Callable

AnyUser = Union[discord.Member, discord.User]
OptAnyUser = Optional[AnyUser]

T = TypeVar("T")
P = ParamSpec("P")
AsyncFunction = Union[Callable[P, Awaitable[T]], Callable]