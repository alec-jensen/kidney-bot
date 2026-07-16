# Database wrapper
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import asyncio
import logging
from typing import Any, TypeVar, cast

from pymongo import ASCENDING, AsyncMongoClient
from pymongo.errors import OperationFailure

from utils.cache import Cache

# ── Helpers ───────────────────────────────────────────────────────────────────

def convert_except_none(value: Any, type: type[Any], default: Any = None, error: bool = True) -> Any:
    if value is None:
        return None
    try:
        return type(value)
    except (ValueError, TypeError):
        if error:
            raise ValueError(f'Could not convert {value!r} to {type}')
        return default


def remove_none_values(dictionary: dict) -> dict:
    return {k: v for k, v in dictionary.items() if v is not None}


# ── Schemas ───────────────────────────────────────────────────────────────────

class Schemas:
    class BaseSchema:
        def __init__(self) -> None:
            pass

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.BaseSchema':
            raise NotImplementedError

        def to_dict(self) -> dict:
            raise NotImplementedError

        def __str__(self) -> str:
            d = self.to_dict()
            inner = ', '.join(f'{k}={v}' for k, v in d.items())
            return f'{self.__class__.__name__}({inner})'

        def __repr__(self) -> str:
            return self.__str__()

        def __iter__(self):
            yield from self.to_dict().items()

        def __getitem__(self, key: str) -> Any:
            return getattr(self, key)

    class AutoModSettings(BaseSchema):
        def __init__(self, guild_id: int | None = None, log_channel: int | None = None,
                     whitelist: list[int] | None = None) -> None:
            self.guild_id: int | None = convert_except_none(guild_id, int)
            self.log_channel: int | None = convert_except_none(log_channel, int)
            self.whitelist: list[int] | None = convert_except_none(whitelist, list)

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.AutoModSettings':
            if data is None:
                return cls()
            guild_id = data.get('guild_id') or data.get('guild')
            return cls(guild_id, data.get('log_channel'), data.get('whitelist'))

        def to_dict(self) -> dict:
            return remove_none_values({
                'guild_id': self.guild_id, 'log_channel': self.log_channel,
                'whitelist': self.whitelist,
            })

    class Currency(BaseSchema):
        def __init__(self, user_id: str | None = None, wallet: int | None = None,
                     bank: int | None = None, inventory: dict | None = None) -> None:
            self.user_id: str | None = convert_except_none(user_id, str)
            self.wallet: int | None = convert_except_none(wallet, int)
            self.bank: int | None = convert_except_none(bank, int)
            self.inventory: dict | None = inventory

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.Currency':
            # support legacy 'userID' field name
            if data is None:
                return cls()
            user_id = data.get('user_id') or data.get('userID')
            return cls(user_id, data.get('wallet'), data.get('bank'), data.get('inventory'))

        def to_dict(self) -> dict:
            return remove_none_values({
                'user_id': self.user_id, 'wallet': self.wallet,
                'bank': self.bank, 'inventory': self.inventory,
            })

    class ScammerList(BaseSchema):
        def __init__(self, user_id: int | None = None, time: int | None = None,
                     reason: str | None = None) -> None:
            self.user_id: int | None = convert_except_none(user_id, int)
            self.time: int | None = convert_except_none(time, int)
            self.reason: str | None = convert_except_none(reason, str)

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.ScammerList':
            # support legacy 'user' field name
            if data is None:
                return cls()
            user_id = data.get('user_id') or data.get('user')
            return cls(user_id, data.get('time'), data.get('reason'))

        def to_dict(self) -> dict:
            return remove_none_values({'user_id': self.user_id, 'time': self.time, 'reason': self.reason})

    class ServerBans(BaseSchema):
        def __init__(self, id: int | None = None, name: int | None = None,
                     owner: int | None = None, reason: str | None = None) -> None:
            self.id: int | None = convert_except_none(id, int)
            self.name: int | None = convert_except_none(name, int)
            self.owner: int | None = convert_except_none(owner, int)
            self.reason: str | None = convert_except_none(reason, str)

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.ServerBans':
            if data is None:
                return cls()
            return cls(data.get('id'), data.get('name'), data.get('owner'), data.get('reason'))

        def to_dict(self) -> dict:
            return remove_none_values({'id': self.id, 'name': self.name, 'owner': self.owner, 'reason': self.reason})

    class RoleSchema(BaseSchema):
        def __init__(self, id: int | None = None, delay: int | None = None) -> None:
            self.id: int | None = convert_except_none(id, int)
            self.delay: int | None = convert_except_none(delay, int)

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.RoleSchema':
            if data is None:
                return cls()
            return cls(data.get('id'), data.get('delay'))

        def to_dict(self) -> dict:
            return remove_none_values({'id': self.id, 'delay': self.delay})

    class AutoRoleSettings(BaseSchema):
        def __init__(self, guild_id: int | None = None,
                     roles: list | None = None,
                     bots_get_roles: bool | None = None) -> None:
            self.guild_id: int | None = convert_except_none(guild_id, int)
            self.roles: list | None = roles
            self.bots_get_roles: bool | None = convert_except_none(bots_get_roles, bool)

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.AutoRoleSettings':
            if data is None:
                return cls()
            guild_id = data.get('guild_id') or data.get('guild')
            # support legacy 'BotsGetRoles' field name
            bots_get_roles = data.get('bots_get_roles') if data.get('bots_get_roles') is not None else data.get('BotsGetRoles')
            return cls(guild_id, data.get('roles'), bots_get_roles)

        def to_dict(self) -> dict:
            return remove_none_values({
                'guild_id': self.guild_id,
                'roles': self.roles,
                'bots_get_roles': self.bots_get_roles,
            })

    class ExceptionSchema(BaseSchema):
        def __init__(self, user_id: int | None = None, always_report_errors: bool | None = None) -> None:
            self.user_id: int | None = convert_except_none(user_id, int)
            self.always_report_errors: bool | None = convert_except_none(always_report_errors, bool)

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.ExceptionSchema':
            if data is None:
                return cls()
            return cls(data.get('user_id'), data.get('always_report_errors'))

        def to_dict(self) -> dict:
            return remove_none_values({'user_id': self.user_id, 'always_report_errors': self.always_report_errors})

    class UserConfig(BaseSchema):
        def __init__(self, user_id: int | None = None, announce_level: int | None = None,
                     ephemeral_moderation_messages: bool | None = None) -> None:
            self.user_id: int | None = convert_except_none(user_id, int)
            self.announce_level: int | None = convert_except_none(announce_level, int)
            self.ephemeral_moderation_messages: bool | None = convert_except_none(ephemeral_moderation_messages, bool)

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.UserConfig':
            if data is None:
                return cls()
            return cls(data.get('user_id'), data.get('announce_level'), data.get('ephemeral_moderation_messages'))

        def to_dict(self) -> dict:
            return remove_none_values({
                'user_id': self.user_id, 'announce_level': self.announce_level,
                'ephemeral_moderation_messages': self.ephemeral_moderation_messages,
            })

    class GuildConfig(BaseSchema):
        def __init__(self, guild_id: int | None = None,
                     ephemeral_moderation_messages: bool | None = None,
                     ephemeral_setting_overpowers_user_setting: bool | None = None,
                     invite_log_channel_id: int | None = None) -> None:
            self.guild_id: int | None = convert_except_none(guild_id, int)
            self.ephemeral_moderation_messages: bool | None = convert_except_none(ephemeral_moderation_messages, bool)
            self.ephemeral_setting_overpowers_user_setting: bool | None = convert_except_none(
                ephemeral_setting_overpowers_user_setting, bool)
            self.invite_log_channel_id: int | None = convert_except_none(invite_log_channel_id, int)

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.GuildConfig':
            if data is None:
                return cls()
            return cls(data.get('guild_id'), data.get('ephemeral_moderation_messages'),
                       data.get('ephemeral_setting_overpowers_user_setting'),
                       data.get('invite_log_channel_id'))

        def to_dict(self) -> dict:
            return remove_none_values({
                'guild_id': self.guild_id,
                'ephemeral_moderation_messages': self.ephemeral_moderation_messages,
                'ephemeral_setting_overpowers_user_setting': self.ephemeral_setting_overpowers_user_setting,
                'invite_log_channel_id': self.invite_log_channel_id,
            })

    class ModLogEntry(BaseSchema):
        ACTION_TYPES = ("warn", "mute", "tempmute", "kick", "ban", "unmute", "unban", "nickname", "purge")

        def __init__(self, id: str | None = None, guild_id: int | None = None,
                     user_id: int | None = None, moderator_id: int | None = None,
                     action_type: str | None = None, reason: str | None = None,
                     timestamp: int | None = None, duration: int | None = None,
                     expires_at: int | None = None) -> None:
            self.id: str | None = convert_except_none(id, str)
            self.guild_id: int | None = convert_except_none(guild_id, int)
            self.user_id: int | None = convert_except_none(user_id, int)
            self.moderator_id: int | None = convert_except_none(moderator_id, int)
            self.action_type: str | None = convert_except_none(action_type, str)
            self.reason: str | None = convert_except_none(reason, str)
            self.timestamp: int | None = convert_except_none(timestamp, int)
            self.duration: int | None = convert_except_none(duration, int)
            self.expires_at: int | None = convert_except_none(expires_at, int)

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.ModLogEntry':
            if data is None:
                return cls()
            return cls(
                data.get('id'), data.get('guild_id'), data.get('user_id'),
                data.get('moderator_id'), data.get('action_type'), data.get('reason'),
                data.get('timestamp'), data.get('duration'), data.get('expires_at'),
            )

        def to_dict(self) -> dict:
            return remove_none_values({
                'id': self.id, 'guild_id': self.guild_id, 'user_id': self.user_id,
                'moderator_id': self.moderator_id, 'action_type': self.action_type,
                'reason': self.reason, 'timestamp': self.timestamp,
                'duration': self.duration, 'expires_at': self.expires_at,
            })

    class ModConfig(BaseSchema):
        def __init__(self, guild_id: int | None = None, log_channel_id: int | None = None,
                     escalation_rules: list[dict] | None = None,
                     require_reason: bool | None = None) -> None:
            self.guild_id: int | None = convert_except_none(guild_id, int)
            self.log_channel_id: int | None = convert_except_none(log_channel_id, int)
            self.escalation_rules: list[dict] | None = escalation_rules
            self.require_reason: bool | None = convert_except_none(require_reason, bool)

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.ModConfig':
            if data is None:
                return cls()
            return cls(data.get('guild_id'), data.get('log_channel_id'), data.get('escalation_rules'),
                       data.get('require_reason'))

        def to_dict(self) -> dict:
            return remove_none_values({
                'guild_id': self.guild_id,
                'log_channel_id': self.log_channel_id,
                'escalation_rules': self.escalation_rules,
                'require_reason': self.require_reason,
            })

    class JoinTrack(BaseSchema):
        """Post-join monitoring record for a member during their tracking window."""
        def __init__(self, id: str | None = None, guild_id: int | None = None,
                     user_id: int | None = None, joined_at: int | None = None,
                     expires_at: int | None = None, score: int | None = None,
                     signals: list[dict] | None = None, invite_code: str | None = None,
                     channels_messaged: list[tuple[int, int]] | None = None,
                     message_count: int | None = None,
                     first_message_at: int | None = None,
                     total_mentions: int | None = None,
                     kicked_for_verification: bool | None = None,
                     behavioral_score: int | None = None,
                     inviter_id: int | None = None,
                     mod_confirmed: bool | None = None,
                     mod_false_positive: bool | None = None) -> None:
            self.id: str | None = convert_except_none(id, str)
            self.guild_id: int | None = convert_except_none(guild_id, int)
            self.user_id: int | None = convert_except_none(user_id, int)
            self.joined_at: int | None = convert_except_none(joined_at, int)
            self.expires_at: int | None = convert_except_none(expires_at, int)
            # Join-time static score (never changes after initial evaluation)
            self.score: int | None = convert_except_none(score, int)
            # Latest behavioral score (replaces on each message evaluation, not additive)
            self.behavioral_score: int = convert_except_none(behavioral_score, int) or 0
            self.signals: list[dict] | None = signals
            self.invite_code: str | None = convert_except_none(invite_code, str)
            self.channels_messaged: list[tuple[int, int]] = channels_messaged or []  # (channel_id, timestamp)
            self.message_count: int = convert_except_none(message_count, int) or 0
            self.first_message_at: int | None = convert_except_none(first_message_at, int)
            self.total_mentions: int = convert_except_none(total_mentions, int) or 0
            self.kicked_for_verification: bool | None = convert_except_none(kicked_for_verification, bool)
            # User ID of whoever created the invite this member used (for invite trees).
            self.inviter_id: int | None = convert_except_none(inviter_id, int)
            # Feedback loop: True when a mod manually confirmed the bot's flag was correct.
            self.mod_confirmed: bool | None = convert_except_none(mod_confirmed, bool)
            # Feedback loop: True when a mod reversed the bot's automated action (false positive).
            self.mod_false_positive: bool | None = convert_except_none(mod_false_positive, bool)

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.JoinTrack':
            if data is None:
                return cls()
            return cls(
                data.get('id'), data.get('guild_id'), data.get('user_id'),
                data.get('joined_at'), data.get('expires_at'), data.get('score'),
                data.get('signals'), data.get('invite_code'),
                data.get('channels_messaged'), data.get('message_count'),
                data.get('first_message_at'), data.get('total_mentions'),
                data.get('kicked_for_verification'), data.get('behavioral_score'),
                data.get('inviter_id'), data.get('mod_confirmed'), data.get('mod_false_positive'),
            )

        def to_dict(self) -> dict:
            d = remove_none_values({
                'id': self.id, 'guild_id': self.guild_id, 'user_id': self.user_id,
                'joined_at': self.joined_at, 'expires_at': self.expires_at,
                'score': self.score, 'signals': self.signals,
                'invite_code': self.invite_code,
                'first_message_at': self.first_message_at,
                'kicked_for_verification': self.kicked_for_verification,
                'inviter_id': self.inviter_id,
                'mod_confirmed': self.mod_confirmed,
                'mod_false_positive': self.mod_false_positive,
            })
            d['channels_messaged'] = self.channels_messaged
            d['message_count'] = self.message_count
            d['total_mentions'] = self.total_mentions
            d['behavioral_score'] = self.behavioral_score
            return d

    class MusicQueue(BaseSchema):
        def __init__(self, guild_id: int | None = None, voice_channel_id: int | None = None,
                     text_channel_id: int | None = None, current: dict | None = None,
                     queue: list | None = None, loop_mode: str | None = None,
                     volume: float | None = None) -> None:
            self.guild_id: int | None = convert_except_none(guild_id, int)
            self.voice_channel_id: int | None = convert_except_none(voice_channel_id, int)
            self.text_channel_id: int | None = convert_except_none(text_channel_id, int)
            self.current: dict | None = current
            self.queue: list = queue if queue is not None else []
            self.loop_mode: str | None = convert_except_none(loop_mode, str)
            self.volume: float | None = convert_except_none(volume, float)

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.MusicQueue':
            if data is None:
                return cls()
            return cls(data.get('guild_id'), data.get('voice_channel_id'), data.get('text_channel_id'),
                       data.get('current'), data.get('queue', []), data.get('loop_mode'), data.get('volume'))

        def to_dict(self) -> dict:
            d = remove_none_values({
                'guild_id': self.guild_id, 'voice_channel_id': self.voice_channel_id,
                'text_channel_id': self.text_channel_id, 'current': self.current,
                'loop_mode': self.loop_mode, 'volume': self.volume,
            })
            d['queue'] = self.queue
            return d

    class GuildHeuristicsConfig(BaseSchema):
        def __init__(self, guild_id: int | None = None, enabled: bool | None = None,
                     tracking_days: int | None = None, alert_channel_id: int | None = None,
                     weight_overrides: dict | None = None,
                     threshold_overrides: dict | None = None,
                     action_overrides: dict | None = None,
                     review_channel_id: int | None = None,
                     auto_delete_on_ban: bool | None = None,
                     auto_delete_seconds: int | None = None,
                     auto_delete_score_threshold: int | None = None) -> None:
            self.guild_id: int | None = convert_except_none(guild_id, int)
            self.enabled: bool | None = convert_except_none(enabled, bool)
            self.tracking_days: int | None = convert_except_none(tracking_days, int)
            self.alert_channel_id: int | None = convert_except_none(alert_channel_id, int)
            # Separate channel for the mod review queue (borderline scores, no auto-action).
            self.review_channel_id: int | None = convert_except_none(review_channel_id, int)
            self.weight_overrides: dict | None = weight_overrides
            self.threshold_overrides: dict | None = threshold_overrides
            self.action_overrides: dict | None = action_overrides
            # When True, automatically deletes message history up to auto_delete_seconds on auto-ban.
            self.auto_delete_on_ban: bool | None = convert_except_none(auto_delete_on_ban, bool)
            # How far back to delete messages (seconds). None → 86400 (24 hours).
            self.auto_delete_seconds: int | None = convert_except_none(auto_delete_seconds, int)
            # Minimum score for auto-delete to apply. None → applies to all auto-bans.
            self.auto_delete_score_threshold: int | None = convert_except_none(auto_delete_score_threshold, int)

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.GuildHeuristicsConfig':
            if data is None:
                return cls()
            return cls(
                data.get('guild_id'), data.get('enabled'), data.get('tracking_days'),
                data.get('alert_channel_id'), data.get('weight_overrides'),
                data.get('threshold_overrides'), data.get('action_overrides'),
                data.get('review_channel_id'),
                data.get('auto_delete_on_ban'), data.get('auto_delete_seconds'),
                data.get('auto_delete_score_threshold'),
            )

        def to_dict(self) -> dict:
            return remove_none_values({
                'guild_id': self.guild_id, 'enabled': self.enabled,
                'tracking_days': self.tracking_days, 'alert_channel_id': self.alert_channel_id,
                'review_channel_id': self.review_channel_id,
                'weight_overrides': self.weight_overrides,
                'threshold_overrides': self.threshold_overrides,
                'action_overrides': self.action_overrides,
                'auto_delete_on_ban': self.auto_delete_on_ban,
                'auto_delete_seconds': self.auto_delete_seconds,
                'auto_delete_score_threshold': self.auto_delete_score_threshold,
            })

    class BotGuild(BaseSchema):
        """Mirrors guild presence/metadata so external services (e.g. the web
        dashboard) can tell which guilds the bot is in without a live gateway
        connection — populated solely by bot-side listeners."""

        def __init__(self, guild_id: int | None = None, name: str | None = None,
                     icon: str | None = None, member_count: int | None = None,
                     owner_id: int | None = None) -> None:
            self.guild_id: int | None = convert_except_none(guild_id, int)
            self.name: str | None = convert_except_none(name, str)
            self.icon: str | None = convert_except_none(icon, str)
            self.member_count: int | None = convert_except_none(member_count, int)
            self.owner_id: int | None = convert_except_none(owner_id, int)

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.BotGuild':
            if data is None:
                return cls()
            return cls(
                data.get('guild_id'), data.get('name'), data.get('icon'),
                data.get('member_count'), data.get('owner_id'),
            )

        def to_dict(self) -> dict:
            return remove_none_values({
                'guild_id': self.guild_id, 'name': self.name, 'icon': self.icon,
                'member_count': self.member_count, 'owner_id': self.owner_id,
            })

    class HoneypotConfig(BaseSchema):
        def __init__(self, guild_id: int | None = None, channel_id: int | None = None,
                     verify_role_id: int | None = None, pending_role_id: int | None = None,
                     mode: str | None = None, message_action: str | None = None,
                     alert_channel_id: int | None = None, enabled: bool | None = None,
                     message_id: int | None = None) -> None:
            self.guild_id: int | None = convert_except_none(guild_id, int)
            self.channel_id: int | None = convert_except_none(channel_id, int)
            self.verify_role_id: int | None = convert_except_none(verify_role_id, int)
            self.pending_role_id: int | None = convert_except_none(pending_role_id, int)
            self.mode: str | None = convert_except_none(mode, str)
            self.message_action: str | None = convert_except_none(message_action, str)
            self.alert_channel_id: int | None = convert_except_none(alert_channel_id, int)
            self.enabled: bool | None = convert_except_none(enabled, bool)
            self.message_id: int | None = convert_except_none(message_id, int)

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.HoneypotConfig':
            if data is None:
                return cls()
            return cls(
                data.get('guild_id'), data.get('channel_id'), data.get('verify_role_id'),
                data.get('pending_role_id'), data.get('mode'), data.get('message_action'),
                data.get('alert_channel_id'), data.get('enabled'), data.get('message_id'),
            )

        def to_dict(self) -> dict:
            return remove_none_values({
                'guild_id': self.guild_id, 'channel_id': self.channel_id,
                'verify_role_id': self.verify_role_id, 'pending_role_id': self.pending_role_id,
                'mode': self.mode, 'message_action': self.message_action,
                'alert_channel_id': self.alert_channel_id, 'enabled': self.enabled,
                'message_id': self.message_id,
            })

    class Network(BaseSchema):
        def __init__(self, id: str | None = None, name: str | None = None,
                     owner_id: int | None = None, guild_ids: list | None = None,
                     log_server_id: int | None = None, log_channel_map: dict | None = None,
                     invite_code: str | None = None, invite_expires_at: int | None = None,
                     propagate_bans: bool | None = None, propagate_kicks: bool | None = None,
                     propagate_mutes: bool | None = None, share_heuristics: bool | None = None,
                     sync_raid_alerts: bool | None = None,
                     watchlist: list | None = None) -> None:
            self.id: str | None = convert_except_none(id, str)
            self.name: str | None = convert_except_none(name, str)
            self.owner_id: int | None = convert_except_none(owner_id, int)
            self.guild_ids: list[int] = guild_ids if guild_ids is not None else []
            self.log_server_id: int | None = convert_except_none(log_server_id, int)
            self.log_channel_map: dict = log_channel_map if log_channel_map is not None else {}
            self.invite_code: str | None = convert_except_none(invite_code, str)
            self.invite_expires_at: int | None = convert_except_none(invite_expires_at, int)
            self.propagate_bans: bool = bool(propagate_bans) if propagate_bans is not None else True
            self.propagate_kicks: bool = bool(propagate_kicks) if propagate_kicks is not None else False
            self.propagate_mutes: bool = bool(propagate_mutes) if propagate_mutes is not None else False
            self.share_heuristics: bool = bool(share_heuristics) if share_heuristics is not None else True
            self.sync_raid_alerts: bool = bool(sync_raid_alerts) if sync_raid_alerts is not None else True
            self.watchlist: list[dict] = watchlist if watchlist is not None else []

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.Network':
            if data is None:
                return cls()
            return cls(
                data.get('id'), data.get('name'), data.get('owner_id'),
                data.get('guild_ids'), data.get('log_server_id'), data.get('log_channel_map'),
                data.get('invite_code'), data.get('invite_expires_at'),
                data.get('propagate_bans'), data.get('propagate_kicks'),
                data.get('propagate_mutes'), data.get('share_heuristics'),
                data.get('sync_raid_alerts'), data.get('watchlist'),
            )

        def to_dict(self) -> dict:
            d = remove_none_values({
                'id': self.id, 'name': self.name, 'owner_id': self.owner_id,
                'log_server_id': self.log_server_id, 'invite_code': self.invite_code,
                'invite_expires_at': self.invite_expires_at,
            })
            d['guild_ids'] = self.guild_ids
            d['log_channel_map'] = self.log_channel_map
            d['propagate_bans'] = self.propagate_bans
            d['propagate_kicks'] = self.propagate_kicks
            d['propagate_mutes'] = self.propagate_mutes
            d['share_heuristics'] = self.share_heuristics
            d['sync_raid_alerts'] = self.sync_raid_alerts
            d['watchlist'] = self.watchlist
            return d

    class NetworkGuildConfig(BaseSchema):
        def __init__(self, guild_id: int | None = None, network_id: str | None = None,
                     is_log_server: bool | None = None) -> None:
            self.guild_id: int | None = convert_except_none(guild_id, int)
            self.network_id: str | None = convert_except_none(network_id, str)
            self.is_log_server: bool = bool(is_log_server) if is_log_server is not None else False

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.NetworkGuildConfig':
            if data is None:
                return cls()
            return cls(data.get('guild_id'), data.get('network_id'), data.get('is_log_server'))

        def to_dict(self) -> dict:
            return remove_none_values({
                'guild_id': self.guild_id, 'network_id': self.network_id,
                'is_log_server': self.is_log_server,
            })

    class NetworkUserRep(BaseSchema):
        def __init__(self, id: str | None = None, network_id: str | None = None,
                     user_id: int | None = None, flag_count: int | None = None,
                     action_count: int | None = None, last_flagged_at: int | None = None,
                     guilds_flagged: list | None = None,
                     trusted_in_guilds: list | None = None,
                     trusted_since: int | None = None) -> None:
            self.id: str | None = convert_except_none(id, str)
            self.network_id: str | None = convert_except_none(network_id, str)
            self.user_id: int | None = convert_except_none(user_id, int)
            self.flag_count: int = convert_except_none(flag_count, int) or 0
            self.action_count: int = convert_except_none(action_count, int) or 0
            self.last_flagged_at: int | None = convert_except_none(last_flagged_at, int)
            self.guilds_flagged: list[int] = guilds_flagged if guilds_flagged is not None else []
            self.trusted_in_guilds: list[int] = trusted_in_guilds if trusted_in_guilds is not None else []
            self.trusted_since: int | None = convert_except_none(trusted_since, int)

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.NetworkUserRep':
            if data is None:
                return cls()
            return cls(
                data.get('id'), data.get('network_id'), data.get('user_id'),
                data.get('flag_count'), data.get('action_count'), data.get('last_flagged_at'),
                data.get('guilds_flagged'), data.get('trusted_in_guilds'), data.get('trusted_since'),
            )

        def to_dict(self) -> dict:
            d = remove_none_values({
                'id': self.id, 'network_id': self.network_id, 'user_id': self.user_id,
                'last_flagged_at': self.last_flagged_at, 'trusted_since': self.trusted_since,
            })
            d['flag_count'] = self.flag_count
            d['action_count'] = self.action_count
            d['guilds_flagged'] = self.guilds_flagged
            d['trusted_in_guilds'] = self.trusted_in_guilds
            return d


T = TypeVar('T', bound=Schemas.BaseSchema)


# ── Collection ────────────────────────────────────────────────────────────────


class Collection[T: Schemas.BaseSchema]:
    """Typed async wrapper around a pymongo collection with an O(1) pk cache.

    All methods accept and return schema objects — raw dicts never leave this class.
    """

    def __init__(self, collection: Any, primary_key: str,
                 schema_class: type[T],
                 cache_ttl: int = 300,
                 legacy_pk: str | None = None) -> None:
        self.collection = collection
        self._pk = primary_key
        self._legacy_pk = legacy_pk
        self._schema: type[T] = schema_class
        self.cache: Cache = Cache(primary_key, ttl=cache_ttl)

    def _from_doc(self, doc: dict) -> T:
        return cast(T, self._schema.from_dict(doc))

    async def get(self, pk_value: Any, **extra_filters: Any) -> T | None:
        """Return the schema for this primary key, or None if not found."""
        query = {self._pk: pk_value, **extra_filters}

        # Only use the cache for simple pk-only lookups
        if not extra_filters:
            cached = self.cache.get_one(query)
            if cached is not None:
                return self._from_doc(cached)

        doc = await self.collection.find_one(query)

        if doc is None and self._legacy_pk and not extra_filters:
            doc = await self.collection.find_one({self._legacy_pk: pk_value})

        if doc is None:
            return None
        if not extra_filters:
            self.cache.add(doc)
        return self._from_doc(doc)

    async def all(self, limit: int = 1000) -> list[T]:
        """Return all documents in the collection as schema objects."""
        cursor = self.collection.find({})
        if limit:
            cursor = cursor.limit(limit)
        docs = await cursor.to_list(length=limit)
        self.cache.add_many(docs)
        return [self._from_doc(d) for d in docs]

    async def save(self, schema: T) -> None:
        """Upsert by primary key. Migrates legacy field names on first write."""
        doc = schema.to_dict()
        pk_val = doc.get(self._pk)

        existing_id = None
        existing = await self.collection.find_one({self._pk: pk_val})
        if existing is None and self._legacy_pk:
            existing = await self.collection.find_one({self._legacy_pk: pk_val})
        if existing is not None:
            existing_id = existing['_id']

        if existing_id is not None:
            await self.collection.replace_one({'_id': existing_id}, doc)
        else:
            await self.collection.insert_one(doc)

        self.cache.add(doc)

    async def delete(self, pk_value: Any, **extra_filters: Any) -> None:
        """Delete by primary key."""
        query = {self._pk: pk_value, **extra_filters}
        result = await self.collection.delete_one(query)
        if result.deleted_count == 0 and self._legacy_pk and not extra_filters:
            await self.collection.delete_one({self._legacy_pk: pk_value})
        self.cache.remove({self._pk: pk_value})

    async def exists(self, pk_value: Any, **extra_filters: Any) -> bool:
        return await self.get(pk_value, **extra_filters) is not None

    async def count(self, **filters: Any) -> int:
        return await self.collection.count_documents(filters)

    async def query_one(self, filter_dict: dict) -> T | None:
        """Escape hatch for complex queries. Returns a schema object."""
        doc = await self.collection.find_one(filter_dict)
        if doc is None:
            return None
        return self._from_doc(doc)

    async def query_many(self, filter_dict: dict, limit: int = 1000) -> list[T]:
        """Escape hatch for complex queries. Returns a list of schema objects."""
        cursor = self.collection.find(filter_dict)
        if limit:
            cursor = cursor.limit(limit)
        docs = await cursor.to_list(length=limit)
        return [self._from_doc(d) for d in docs]


class ModLogCollection(Collection[Schemas.ModLogEntry]):
    """Specialised collection for the mod action log with history query helpers."""

    async def get_user_history(
        self,
        user_id: int,
        guild_id: int,
        since: int | None = None,
        action_types: list[str] | None = None,
        limit: int = 500,
    ) -> list[Schemas.ModLogEntry]:
        filter_dict: dict[str, Any] = {"user_id": user_id, "guild_id": guild_id}
        if since is not None:
            filter_dict["timestamp"] = {"$gte": since}
        if action_types:
            filter_dict["action_type"] = {"$in": action_types}
        return await self.query_many(filter_dict, limit=limit)

    async def delete_user_history(self, user_id: int, guild_id: int) -> int:
        result = await self.collection.delete_many({"user_id": user_id, "guild_id": guild_id})
        return result.deleted_count


class JoinTrackCollection(Collection[Schemas.JoinTrack]):
    """Collection for post-join monitoring records."""

    async def get_user_track(self, guild_id: int, user_id: int) -> Schemas.JoinTrack | None:
        return await self.query_one({"guild_id": guild_id, "user_id": user_id})

    async def upsert_for_member(self, track: Schemas.JoinTrack) -> None:
        """Insert or replace the single tracking record for (guild_id, user_id)."""
        existing = await self.get_user_track(
            track.guild_id or 0, track.user_id or 0)
        if existing is not None and existing.id is not None:
            track.id = existing.id
        if track.id is None:
            from uuid import uuid4
            track.id = str(uuid4())
        await self.save(track)

    async def get_recent_joins(self, guild_id: int, since: int) -> list[Schemas.JoinTrack]:
        return await self.query_many(
            {"guild_id": guild_id, "joined_at": {"$gte": since}})

    async def get_invitees(self, guild_id: int, inviter_id: int) -> list[Schemas.JoinTrack]:
        """Return all tracks in this guild where the member used an invite created by inviter_id."""
        return await self.query_many({"guild_id": guild_id, "inviter_id": inviter_id})

    async def expire_and_get(self, now: int) -> tuple[list[Schemas.JoinTrack], int]:
        """Fetch all expired tracks (for processing), then delete them atomically."""
        expired = await self.query_many({"expires_at": {"$lte": now}})
        result = await self.collection.delete_many({"expires_at": {"$lte": now}})
        return expired, result.deleted_count

    async def delete_expired(self, now: int) -> int:
        result = await self.collection.delete_many({"expires_at": {"$lte": now}})
        return result.deleted_count


class NetworkCollection(Collection[Schemas.Network]):
    async def get_by_owner(self, owner_id: int) -> Schemas.Network | None:
        return await self.query_one({"owner_id": owner_id})

    async def get_for_guild(self, guild_id: int) -> Schemas.Network | None:
        return await self.query_one({"guild_ids": guild_id})


class NetworkUserRepCollection(Collection[Schemas.NetworkUserRep]):
    async def get_user_rep(self, network_id: str, user_id: int) -> Schemas.NetworkUserRep | None:
        return await self.query_one({"network_id": network_id, "user_id": user_id})

    async def upsert_user_rep(self, rep: Schemas.NetworkUserRep) -> None:
        existing = await self.get_user_rep(rep.network_id or "", rep.user_id or 0)
        if existing is not None and existing.id is not None:
            rep.id = existing.id
        if rep.id is None:
            from uuid import uuid4
            rep.id = str(uuid4())
        await self.save(rep)


# ── Database ──────────────────────────────────────────────────────────────────

class Database:
    def __init__(self, dbstring: str) -> None:
        self.dbstring = dbstring
        self.connected = False
        self._cleanup_task: asyncio.Task | None = None

    async def connect(self) -> None:
        if self.connected:
            return

        logging.info('Connecting to database.')
        self.client: AsyncMongoClient = AsyncMongoClient(
            self.dbstring, serverSelectionTimeoutMS=5000)

        try:
            await self.client.server_info()
        except Exception as e:
            logging.critical('Failed to connect to database.')
            raise e

        logging.info('Connected to database.')
        self.connected = True

        db = self.client.data

        self.automodsettings: Collection[Schemas.AutoModSettings] = Collection(
            db.automodsettings, 'guild_id', Schemas.AutoModSettings, legacy_pk='guild')
        self.currency: Collection[Schemas.Currency] = Collection(
            db.currency, 'user_id', Schemas.Currency, legacy_pk='userID')
        self.scammer_list: Collection[Schemas.ScammerList] = Collection(
            db.scammer_list, 'user_id', Schemas.ScammerList, legacy_pk='user')
        self.serverbans: Collection[Schemas.ServerBans] = Collection(
            db.serverbans, 'id', Schemas.ServerBans)
        self.autorolesettings: Collection[Schemas.AutoRoleSettings] = Collection(
            db.autorolesettings, 'guild_id', Schemas.AutoRoleSettings, legacy_pk='guild')
        self.exceptions: Collection[Schemas.ExceptionSchema] = Collection(
            db.exceptions, 'user_id', Schemas.ExceptionSchema)
        self.user_config: Collection[Schemas.UserConfig] = Collection(
            db.user_config, 'user_id', Schemas.UserConfig)
        self.guild_config: Collection[Schemas.GuildConfig] = Collection(
            db.guild_config, 'guild_id', Schemas.GuildConfig)
        self.mod_log: ModLogCollection = ModLogCollection(
            db.mod_log, 'id', Schemas.ModLogEntry)
        self.mod_config: Collection[Schemas.ModConfig] = Collection(
            db.mod_config, 'guild_id', Schemas.ModConfig)
        self.music_queues: Collection[Schemas.MusicQueue] = Collection(
            db.music_queues, 'guild_id', Schemas.MusicQueue)
        self.join_tracks: JoinTrackCollection = JoinTrackCollection(
            db.join_tracks, 'id', Schemas.JoinTrack)
        self.heuristics_config: Collection[Schemas.GuildHeuristicsConfig] = Collection(
            db.heuristics_config, 'guild_id', Schemas.GuildHeuristicsConfig)
        self.honeypot_config: Collection[Schemas.HoneypotConfig] = Collection(
            db.honeypot_config, 'guild_id', Schemas.HoneypotConfig)
        self.networks: NetworkCollection = NetworkCollection(
            db.networks, 'id', Schemas.Network)
        self.network_guild_config: Collection[Schemas.NetworkGuildConfig] = Collection(
            db.network_guild_config, 'guild_id', Schemas.NetworkGuildConfig)
        self.network_user_rep: NetworkUserRepCollection = NetworkUserRepCollection(
            db.network_user_rep, 'id', Schemas.NetworkUserRep)
        self.bot_guilds: Collection[Schemas.BotGuild] = Collection(
            db.bot_guilds, 'guild_id', Schemas.BotGuild)

        self.collections: list[Collection] = [
            self.automodsettings,
            self.currency, self.scammer_list, self.serverbans,
            self.autorolesettings, self.exceptions, self.user_config,
            self.guild_config, self.mod_log, self.mod_config, self.music_queues,
            self.join_tracks, self.heuristics_config, self.honeypot_config,
            self.networks, self.network_guild_config, self.network_user_rep,
            self.bot_guilds,
        ]

        await self._ensure_indexes(db)
        self._cleanup_task = asyncio.create_task(self._cache_cleanup_loop())

    @staticmethod
    async def _create_index(collection: Any, keys: Any, **options: Any) -> None:
        """Create an index, recreating it if a prior run left an incompatible
        definition (e.g. non-sparse before legacy documents were accounted for)."""
        key_spec = [(keys, ASCENDING)] if isinstance(keys, str) else list(keys)
        try:
            await collection.create_index(keys, **options)
        except OperationFailure as e:
            if e.code in (85, 86):  # IndexOptionsConflict / IndexKeySpecsConflict
                async for index in await collection.list_indexes():
                    if list(index["key"].items()) == key_spec:
                        await collection.drop_index(index["name"])
                        break
                await collection.create_index(keys, **options)
            else:
                raise

    async def _ensure_indexes(self, db: Any) -> None:
        # sparse=True so legacy documents that still use the old field names
        # (and therefore lack the new primary key field) don't collide on a
        # shared `null` value when the unique index is built.
        await self._create_index(db.automodsettings, 'guild_id', unique=True, sparse=True)
        await self._create_index(db.autorolesettings, 'guild_id', unique=True, sparse=True)
        await self._create_index(db.guild_config, 'guild_id', unique=True, sparse=True)
        await self._create_index(db.currency, 'user_id', unique=True, sparse=True)
        await self._create_index(db.scammer_list, 'user_id', unique=True, sparse=True)
        await self._create_index(db.user_config, 'user_id', unique=True, sparse=True)
        await self._create_index(db.exceptions, 'user_id', unique=True, sparse=True)
        await self._create_index(db.mod_log, 'id', unique=True, sparse=True)
        await self._create_index(db.mod_log, [('guild_id', ASCENDING), ('user_id', ASCENDING), ('timestamp', ASCENDING)])
        await self._create_index(db.mod_config, 'guild_id', unique=True, sparse=True)
        await self._create_index(db.music_queues, 'guild_id', unique=True, sparse=True)
        await self._create_index(db.join_tracks, 'id', unique=True, sparse=True)
        await self._create_index(db.join_tracks, [('guild_id', ASCENDING), ('user_id', ASCENDING)])
        await self._create_index(db.join_tracks, 'expires_at')
        await self._create_index(db.heuristics_config, 'guild_id', unique=True, sparse=True)
        await self._create_index(db.honeypot_config, 'guild_id', unique=True, sparse=True)
        await self._create_index(db.networks, 'id', unique=True, sparse=True)
        await self._create_index(db.networks, 'owner_id')
        await self._create_index(db.networks, 'guild_ids')
        await self._create_index(db.network_guild_config, 'guild_id', unique=True, sparse=True)
        await self._create_index(db.network_guild_config, 'network_id')
        await self._create_index(db.network_user_rep, 'id', unique=True, sparse=True)
        await self._create_index(
            db.network_user_rep,
            [('network_id', ASCENDING), ('user_id', ASCENDING)])
        await self._create_index(db.bot_guilds, 'guild_id', unique=True, sparse=True)

    async def _cache_cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            for col in self.collections:
                col.cache.cleanup()
