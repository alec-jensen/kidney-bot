# This file contains functions for working with the audit log
# Copyright (C) 2023 Alec Jensen
# Full license at LICENSE.md
# type: ignore

import discord
import logging
from typing import Union
from utils.kidney_bot import KidneyBot


class AuditLogCheckTypes:
    moderation_actions = [discord.AuditLogAction.member_role_update, discord.AuditLogAction.member_update,
                          discord.AuditLogAction.guild_update, discord.AuditLogAction.role_create,
                          discord.AuditLogAction.role_delete, discord.AuditLogAction.role_update,
                          discord.AuditLogAction.channel_create, discord.AuditLogAction.channel_delete,
                          discord.AuditLogAction.channel_update, discord.AuditLogAction.overwrite_create,
                          discord.AuditLogAction.overwrite_delete, discord.AuditLogAction.overwrite_update,
                          discord.AuditLogAction.kick, discord.AuditLogAction.ban, discord.AuditLogAction.unban,
                          discord.AuditLogAction.member_prune, discord.AuditLogAction.member_move,
                          discord.AuditLogAction.member_disconnect, discord.AuditLogAction.bot_add,
                          discord.AuditLogAction.webhook_create, discord.AuditLogAction.webhook_update,
                          discord.AuditLogAction.webhook_delete, discord.AuditLogAction.emoji_create,
                          discord.AuditLogAction.emoji_delete, discord.AuditLogAction.emoji_update,
                          discord.AuditLogAction.sticker_create, discord.AuditLogAction.sticker_delete,
                          discord.AuditLogAction.sticker_update, discord.AuditLogAction.stage_instance_create,
                          discord.AuditLogAction.stage_instance_delete, discord.AuditLogAction.stage_instance_update,
                          discord.AuditLogAction.message_delete, discord.AuditLogAction.message_bulk_delete,
                          discord.AuditLogAction.message_pin, discord.AuditLogAction.message_unpin,
                          discord.AuditLogAction.integration_create, discord.AuditLogAction.integration_update,
                          discord.AuditLogAction.integration_delete, discord.AuditLogAction.thread_create,
                          discord.AuditLogAction.scheduled_event_create, discord.AuditLogAction.scheduled_event_update,
                          discord.AuditLogAction.scheduled_event_delete, discord.AuditLogAction.app_command_permission_update,
                          discord.AuditLogAction.automod_rule_create, discord.AuditLogAction.automod_rule_update,
                          discord.AuditLogAction.automod_rule_delete]


"""Attempt to undo an action in the audit log. Returns True if successful, False if not, and None if it is partially undone."""


async def attempt_undo_audit_log_action(entry: discord.AuditLogEntry, client: KidneyBot | None = None) -> bool | None:  # type: ignore
    # https://discordpy.readthedocs.io/en/stable/api.html?highlight=auditlogaction#discord.AuditLogAction
    # This function has complex Discord.py audit log handling that would require extensive refactoring to type properly
    # Using type: ignore for the entire function body as it deals with many different audit log target types

    # We use getattr() here because some of the attributes are optional and will throw an error if they don't exist

    if entry.action == discord.AuditLogAction.guild_update:
        if not isinstance(entry.target, discord.Guild):
            return False
            
        if getattr(entry.before, "afk_channel", None) != getattr(entry.after, "afk_channel", None):
            await entry.target.edit(afk_channel=entry.before.afk_channel)  # type: ignore
            return True

        if getattr(entry.before, "system_channel", None) != getattr(entry.after, "system_channel", None):
            await entry.target.edit(system_channel=entry.before.system_channel)  # type: ignore
            return True

        if getattr(entry.before, "afk_timeout", None) != getattr(entry.after, "afk_timeout", None):
            await entry.target.edit(afk_timeout=entry.before.afk_timeout)  # type: ignore
            return True

        if getattr(entry.before, "default_notifications", None) != getattr(entry.after, "default_notifications", None):
            await entry.target.edit(default_notifications=entry.before.default_notifications)  # type: ignore
            return True

        if getattr(entry.before, "explicit_content_filter", None) != getattr(entry.after, "explicit_content_filter", None):
            await entry.target.edit(explicit_content_filter=entry.before.explicit_content_filter)  # type: ignore
            return True

        if getattr(entry.before, "mfa_level", None) != getattr(entry.after, "mfa_level", None):
            return False

        if getattr(entry.before, "name", None) != getattr(entry.after, "name", None):
            await entry.target.edit(name=entry.before.name)  # type: ignore
            return True

        if getattr(entry.before, "owner", None) != getattr(entry.after, "owner", None):
            return False

        if getattr(entry.before, "splash", None) != getattr(entry.after, "splash", None):
            await entry.target.edit(splash=entry.before.splash)  # type: ignore
            return True

        if getattr(entry.before, "discovery_splash", None) != getattr(entry.after, "discovery_splash", None):
            await entry.target.edit(discovery_splash=entry.before.discovery_splash)  # type: ignore
            return True

        if getattr(entry.before, "icon", None) != getattr(entry.after, "icon", None):
            await entry.target.edit(icon=entry.before.icon)  # type: ignore
            return True

        if getattr(entry.before, "banner", None) != getattr(entry.after, "banner", None):
            await entry.target.edit(banner=entry.before.banner)  # type: ignore
            return True

        if getattr(entry.before, "vanity_url_code", None) != getattr(entry.after, "vanity_url_code", None):
            await entry.target.edit(vanity_code=entry.before.vanity_url_code)  # type: ignore
            return True

        if getattr(entry.before, "description", None) != getattr(entry.after, "description", None):
            await entry.target.edit(description=entry.before.description)  # type: ignore
            return True

    if entry.action == discord.AuditLogAction.channel_create:
        if hasattr(entry.target, 'delete'):
            await entry.target.delete(reason="[AUTOMATED ACTION] Moderation action undo")  # type: ignore
        return True

    if entry.action == discord.AuditLogAction.channel_delete:
        if entry.target.type == discord.ChannelType.text:
            entry.guild.create_text_channel(name=entry.target.name,
                                            topic=entry.target.topic,
                                            position=entry.target.position,
                                            nsfw=entry.target.nsfw,
                                            slowmode_delay=entry.target.slowmode_delay,
                                            overwrites=entry.target.overwrites,
                                            category=entry.target.category,
                                            reason="[AUTOMATED ACTION] Moderation action undo")
            return True

        if entry.target.type == discord.ChannelType.voice:
            entry.guild.create_voice_channel(name=entry.target.name,
                                             position=entry.target.position,
                                             bitrate=entry.target.bitrate,
                                             user_limit=entry.target.user_limit,
                                             overwrites=entry.target.overwrites,
                                             category=entry.target.category,
                                             reason="[AUTOMATED ACTION] Moderation action undo")
            return True

        if entry.target.type == discord.ChannelType.category:
            entry.guild.create_category(name=entry.target.name,
                                        position=entry.target.position,
                                        overwrites=entry.target.overwrites,
                                        reason="[AUTOMATED ACTION] Moderation action undo")
            return True

        if entry.target.type == discord.ChannelType.stage_voice:
            entry.guild.create_stage_channel(name=entry.target.name,
                                             topic=entry.target.topic,
                                             position=entry.target.position,
                                             rtc_region=entry.target.rtc_region,
                                             overwrites=entry.target.overwrites,
                                             reason="[AUTOMATED ACTION] Moderation action undo")
            return True

        if entry.target.type == discord.ChannelType.news:
            entry.guild.create_news_channel(name=entry.target.name,
                                            topic=entry.target.topic,
                                            position=entry.target.position,
                                            nsfw=entry.target.nsfw,
                                            overwrites=entry.target.overwrites,
                                            category=entry.target.category,
                                            reason="[AUTOMATED ACTION] Moderation action undo")
            return True

        if entry.target.type == discord.ChannelType.forum:
            entry.guild.create_thread(name=entry.target.name,
                                      topic=entry.target.topic,
                                      message_count=entry.target.message_count,
                                      auto_archive_duration=entry.target.auto_archive_duration,
                                      reason="[AUTOMATED ACTION] Moderation action undo")
            return True

        return False

    if entry.action == discord.AuditLogAction.channel_update:
        if getattr(entry.before, "name", None) != getattr(entry.after, "name", None):
            await entry.target.edit(name=entry.before.name)
            return True

        if getattr(entry.before, "type", None) != getattr(entry.after, "type", None):
            await entry.target.edit(type=entry.before.type)
            return True

        if getattr(entry.before, "position", None) != getattr(entry.after, "position", None):
            await entry.target.edit(position=entry.before.position)
            return True

        # does this even ever do anything? channel overwrites are passed as an overwrite_update, not a channel_update
        if getattr(entry.before, "overwrites", None) != getattr(entry.after, "overwrites", None):
            await entry.target.edit(overwrites=entry.before.overwrites)
            return True

        if getattr(entry.before, "topic", None) != getattr(entry.after, "topic", None):
            await entry.target.edit(topic=entry.before.topic)
            return True

        if getattr(entry.before, "bitrate", None) != getattr(entry.after, "bitrate", None):
            await entry.target.edit(bitrate=entry.before.bitrate)
            return True

        if getattr(entry.before, "rtc_region", None) != getattr(entry.after, "rtc_region", None):
            await entry.target.edit(rtc_region=entry.before.rtc_region)
            return True

        if getattr(entry.before, "video_quality_mode", None) != getattr(entry.after, "video_quality_mode", None):
            await entry.target.edit(video_quality_mode=entry.before.video_quality_mode)
            return True

        if getattr(entry.before, "auto_archive_duration", None) != getattr(entry.after, "auto_archive_duration", None):
            await entry.target.edit(default_auto_archive_duration=entry.before.default_auto_archive_duration)
            return True

        if getattr(entry.before, "nsfw", None) != getattr(entry.after, "nsfw", None):
            await entry.target.edit(nsfw=entry.before.nsfw)
            return True

        if getattr(entry.before, "slowmode_delay", None) != getattr(entry.after, "slowmode_delay", None):
            await entry.target.edit(slowmode_delay=entry.before.slowmode_delay)
            return True

        if getattr(entry.before, "user_limit", None) != getattr(entry.after, "user_limit", None):
            await entry.target.edit(user_limit=entry.before.user_limit)
            return True

    # TODO: implement this
    if entry.action == discord.AuditLogAction.overwrite_create:
        return False

    if entry.action == discord.AuditLogAction.overwrite_delete:
        return False

    if entry.action == discord.AuditLogAction.overwrite_update:
        # Is there a better way to do this?

        """for attr in entry.__dict__:
            logging.info(f"{attr}: {getattr(entry, attr, None)}")

        for change in entry._changes:
            old = change.get("old_value", None)
            new = change.get("new_value", None)"""
            

        return False

    if entry.action == discord.AuditLogAction.kick:
        invite: discord.Invite = await entry.guild.channels[0].create_invite(reason="[AUTOMATED ACTION] Moderation action undo", max_uses=1, max_age=0, unique=True)
        await entry.target.send(f"You have been kicked from {entry.target.guild.name}, which has now been undone. Please rejoin using this invite: {invite.url}")
        return None

    if entry.action == discord.AuditLogAction.member_prune:
        return False

    if entry.action == discord.AuditLogAction.ban:
        await entry.guild.unban(entry.target, reason="[AUTOMATED ACTION] Moderation action undo")
        invite: discord.Invite = await entry.guild.channels[0].create_invite(reason="[AUTOMATED ACTION] Moderation action undo", max_uses=1, max_age=0, unique=True)
        try:
            await entry.target.send(f"You have been banned from {entry.guild.name}, which has now been undone. Please rejoin using this invite: {invite.url}")
        except:
            return None

    if entry.action == discord.AuditLogAction.unban:
        await entry.guild.ban(
            entry.target, reason="[AUTOMATED ACTION] Moderation action undo")
        return True

    if entry.action == discord.AuditLogAction.member_update:
        if getattr(entry.before, "nick", None) != getattr(entry.after, "nick", None):
            await entry.target.edit(nick=entry.before.nick)
            return True

        if getattr(entry.before, "mute", None) != getattr(entry.after, "mute", None):
            await entry.target.edit(mute=entry.before.mute)
            return True

        if getattr(entry.before, "deaf", None) != getattr(entry.after, "deaf", None):
            await entry.target.edit(deafen=entry.before.deaf)
            return True

        if getattr(entry.before, "timed_out_until", None) != getattr(entry.after, "timed_out_until", None):
            await entry.target.edit(timed_out_until=entry.before.timed_out_until)
            return True

    if entry.action == discord.AuditLogAction.member_role_update:
        if getattr(entry.before, "roles", None) != getattr(entry.after, "roles", None):
            # find out which roles were added and which were removed
            added_roles = [role for role in entry.after.roles if role not in entry.before.roles]
            removed_roles = [role for role in entry.before.roles if role not in entry.after.roles]

            # remove the added roles
            await entry.target.remove_roles(*added_roles, reason="[AUTOMATED ACTION] Moderation action undo")

            # add the removed roles
            await entry.target.add_roles(*removed_roles, reason="[AUTOMATED ACTION] Moderation action undo")
            return True

    if entry.action == discord.AuditLogAction.member_move:
        return False

    if entry.action == discord.AuditLogAction.member_disconnect:
        return False

    if entry.action == discord.AuditLogAction.bot_add:
        await entry.target.kick(reason="[AUTOMATED ACTION] Moderation action undo")
        return True

    if entry.action == discord.AuditLogAction.role_create:
        await entry.target.delete(reason="[AUTOMATED ACTION] Moderation action undo")
        return True

    if entry.action == discord.AuditLogAction.role_delete:
        return False

    if entry.action == discord.AuditLogAction.role_update:
        if getattr(entry.before, "colour", None) != getattr(entry.after, "colour", None):
            await entry.target.edit(colour=entry.before.colour)
            return True

        if getattr(entry.before, "mentionable", None) != getattr(entry.after, "mentionable", None):
            await entry.target.edit(mentionable=entry.before.mentionable)
            return True

        if getattr(entry.before, "hoist", None) != getattr(entry.after, "hoist", None):
            await entry.target.edit(hoist=entry.before.hoist)
            return True

        if getattr(entry.before, "icon", None) != getattr(entry.after, "icon", None):
            await entry.target.edit(icon=entry.before.icon)
            return True

        if getattr(entry.before, "unicode_emoji", None) != getattr(entry.after, "unicode_emoji", None):
            await entry.target.edit(unicode_emoji=entry.before.unicode_emoji)
            return True

        if getattr(entry.before, "name", None) != getattr(entry.after, "name", None):
            await entry.target.edit(name=entry.before.name)
            return True

        if getattr(entry.before, "permissions", None) != getattr(entry.after, "permissions", None):
            await entry.target.edit(permissions=entry.before.permissions)
            return True

    if entry.action == discord.AuditLogAction.invite_create:
        await entry.target.delete(reason="[AUTOMATED ACTION] Moderation action undo")
        return True

    if entry.action == discord.AuditLogAction.invite_delete:
        return False

    if entry.action == discord.AuditLogAction.webhook_create:
        for webhook in await entry.guild.webhooks():
            if webhook.id == entry.target.id:
                await webhook.delete(reason="[AUTOMATED ACTION] Moderation action undo")
        return True

    if entry.action == discord.AuditLogAction.webhook_update:
        if getattr(entry.before, "name", None) != getattr(entry.after, "name", None):
            for webhook in await entry.guild.webhooks():
                if webhook.id == entry.target.id:
                    await webhook.edit(name=entry.before.name)
                    return True
            return False

        if getattr(entry.before, "channel", None) != getattr(entry.after, "channel", None):
            for webhook in await entry.guild.webhooks():
                if webhook.id == entry.target.id:
                    await webhook.edit(channel=entry.before.channel)
                    return True
            return False

        if getattr(entry.before, "avatar", None) != getattr(entry.after, "avatar", None):
            return False

    if entry.action == discord.AuditLogAction.webhook_delete:
        return False

    if entry.action == discord.AuditLogAction.emoji_create:
        await entry.target.delete(reason="[AUTOMATED ACTION] Moderation action undo")
        return True

    if entry.action == discord.AuditLogAction.emoji_update:
        if getattr(entry.before, "name", None) != getattr(entry.after, "name", None):
            await entry.target.edit(name=entry.before.name)
            return True

    if entry.action == discord.AuditLogAction.emoji_delete:
        return False

    if entry.action == discord.AuditLogAction.message_delete:
        return False

    if entry.action == discord.AuditLogAction.message_bulk_delete:
        return False

    if entry.action == discord.AuditLogAction.message_pin:
        message: discord.Message = await entry.extra.channel.fetch_message(
            entry.extra.message_id)
        await message.unpin(reason="[AUTOMATED ACTION] Moderation action undo")
        return True

    if entry.action == discord.AuditLogAction.message_unpin:
        message: discord.Message = await entry.extra.channel.fetch_message(
            entry.extra.message_id)
        await message.pin(reason="[AUTOMATED ACTION] Moderation action undo")
        async for message in entry.extra.channel.history(limit=10):
            if message.type == discord.MessageType.pins_add:
                if client is None: return True
                if message.author == getattr(client, "user"):
                    await message.delete()
        return True

    if entry.action == discord.AuditLogAction.integration_create:
        return False

    if entry.action == discord.AuditLogAction.integration_update:
        return False

    if entry.action == discord.AuditLogAction.integration_delete:
        return False

    if entry.action == discord.AuditLogAction.stage_instance_create:
        if type(entry.target) == discord.Object:
            stage_instance = await entry.guild.get_stage_instance(entry.target.id)
            stage_instance.delete(reason="[AUTOMATED ACTION] Moderation action undo")
        else:
            await entry.target.delete(reason="[AUTOMATED ACTION] Moderation action undo")

        return True

    if entry.action == discord.AuditLogAction.stage_instance_update:
        if getattr(entry.before, "topic", None) != getattr(entry.after, "topic", None):
            await entry.target.edit(topic=entry.before.topic)
            return True

        if getattr(entry.before, "privacy_level", None) != getattr(entry.after, "privacy_level", None):
            await entry.target.edit(privacy_level=entry.before.privacy_level)
            return True

    if entry.action == discord.AuditLogAction.stage_instance_delete:
        return False

    if entry.action == discord.AuditLogAction.sticker_create:
        await entry.target.delete(reason="[AUTOMATED ACTION] Moderation action undo")
        return True

    if entry.action == discord.AuditLogAction.sticker_update:
        if getattr(entry.before, "name", None) != getattr(entry.after, "name", None):
            await entry.target.edit(name=entry.before.name)
            return True

        if getattr(entry.before, "emoji", None) != getattr(entry.after, "emoji", None):
            await entry.target.edit(emoji=entry.before.emoji)
            return True

        if getattr(entry.before, "type", None) != getattr(entry.after, "type", None):
            await entry.target.edit(type=entry.before.type)
            return True

        if getattr(entry.before, "format_type", None) != getattr(entry.after, "format_type", None):
            await entry.target.edit(format_type=entry.before.format_type)
            return True

        if getattr(entry.before, "description", None) != getattr(entry.after, "description", None):
            await entry.target.edit(description=entry.before.description)
            return True

        if getattr(entry.before, "available", None) != getattr(entry.after, "available", None):
            await entry.target.edit(available=entry.before.available)
            return True

    if entry.action == discord.AuditLogAction.sticker_delete:
        return False

    if entry.action == discord.AuditLogAction.scheduled_event_create:
        await entry.target.delete(reason="[AUTOMATED ACTION] Moderation action undo")
        return True

    if entry.action == discord.AuditLogAction.scheduled_event_update:
        if getattr(entry.before, "name", None) != getattr(entry.after, "name", None):
            await entry.target.edit(name=entry.before.name)

        if getattr(entry.before, "channel", None) != getattr(entry.after, "channel", None):
            await entry.target.edit(channel=entry.before.channel)

        if getattr(entry.before, "description", None) != getattr(entry.after, "description", None):
            await entry.target.edit(description=entry.before.description)

        if getattr(entry.before, "privacy_level", None) != getattr(entry.after, "privacy_level", None):
            await entry.target.edit(privacy_level=entry.before.privacy_level)

        if getattr(entry.before, "status", None) != getattr(entry.after, "status", None):
            await entry.target.edit(status=entry.before.status)

        if getattr(entry.before, "entity_type", None) != getattr(entry.after, "entity_type", None):
            await entry.target.edit(entity_type=entry.before.entity_type)

        if getattr(entry.before, "cover_image", None) != getattr(entry.after, "cover_image", None):
            await entry.target.edit(cover_image=entry.before.cover_image)

    if entry.action == discord.AuditLogAction.scheduled_event_delete:
        return False

    if entry.action == discord.AuditLogAction.thread_create:
        await entry.target.delete()
        return True

    if entry.action == discord.AuditLogAction.thread_update:
        if type(entry.target) == discord.Object:
            entry.target = entry.guild.get_thread(entry.target.id)

        if getattr(entry.before, "name", None) != getattr(entry.after, "name", None):
            await entry.target.edit(name=entry.before.name)
            return True

        if getattr(entry.before, "archived", None) != getattr(entry.after, "archived", None):
            await entry.target.edit(archived=entry.before.archived)
            return True

        if getattr(entry.before, "locked", None) != getattr(entry.after, "locked", None):
            await entry.target.edit(locked=entry.before.locked)
            return True

        if getattr(entry.before, "auto_archive_duration", None) != getattr(entry.after, "auto_archive_duration", None):
            await entry.target.edit(auto_archive_duration=entry.before.auto_archive_duration)
            return True

        if getattr(entry.before, "inviteable", None) != getattr(entry.after, "inviteable", None):
            await entry.target.edit(inviteable=entry.before.inviteable)
            return True

    if entry.action == discord.AuditLogAction.thread_delete:
        return False

    if entry.action == discord.AuditLogAction.app_command_permission_update:
        return False

    if entry.action == discord.AuditLogAction.automod_rule_create:
        if type(entry.target) == discord.Object:
            entry.target = await entry.guild.fetch_automod_rule(entry.target.id)
        await entry.target.delete(reason="[AUTOMATED ACTION] Moderation action undo")
        return True

    if entry.action == discord.AuditLogAction.automod_rule_update:
        return False

    if entry.action == discord.AuditLogAction.automod_rule_delete:
        return False

    if entry.action in [discord.AuditLogAction.automod_block_message,
                        discord.AuditLogAction.automod_flag_message,
                        discord.AuditLogAction.automod_timeout_member]:
        return False

    return False
