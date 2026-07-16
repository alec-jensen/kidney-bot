# Heuristics engine — pure logic, no Discord or database imports.
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

from __future__ import annotations

import logging
import math
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from utils.heuristics_config import HeuristicsDefaults

# A sample of common Unicode homoglyphs mapped to their ASCII equivalents.
# Extend this table as new impersonation vectors are observed.
_HOMOGLYPHS: dict[str, str] = {
    # Cyrillic lookalikes
    'а': 'a', 'е': 'e', 'о': 'o', 'р': 'p', 'с': 'c',
    'х': 'x', 'ѕ': 's', 'і': 'i', 'ј': 'j', 'ԁ': 'd',
    'ո': 'n', 'һ': 'h',
    # Greek lookalikes
    'ο': 'o', 'ϲ': 'c',
    # IPA / phonetic extensions
    'ɑ': 'a', 'ɡ': 'g', 'ɹ': 'r', 'ʂ': 's',
    # Letterlike symbols
    'ℓ': 'l',
    # Fullwidth latin
    'ｍ': 'm',
}

# Public user flag names that convey trust/human status (negative weight signals).
_TRUSTED_PUBLIC_FLAGS = frozenset({
    'staff', 'partner', 'hypesquad', 'hypesquad_bravery', 'hypesquad_brilliance',
    'hypesquad_balance', 'bug_hunter', 'bug_hunter_level_2',
    'discord_certified_moderator', 'early_supporter', 'active_developer',
    'early_verified_bot_developer', 'verified_bot_developer',
})

_URL_RE = re.compile(r'https?://', re.IGNORECASE)


@dataclass
class SignalFiring:
    signal_id: str
    score_delta: int
    detail: str


@dataclass
class HeuristicsResult:
    user_id: int
    guild_id: int
    score: int
    signals: list[SignalFiring]

    def describe(self) -> str:
        if not self.signals:
            return "No suspicious signals detected."
        lines = [f"**Score: {self.score}/100**"]
        for s in self.signals:
            sign = '+' if s.score_delta >= 0 else ''
            lines.append(f"`{sign}{s.score_delta}` {s.detail}")
        return "\n".join(lines)


@dataclass
class PostJoinState:
    """Snapshot of a tracked member's accumulated post-join behavioural data."""
    message_count: int = 0
    channels_messaged: list[tuple[int, int]] = field(default_factory=list)  # (channel_id, timestamp)
    first_message_at: int | None = None
    total_mentions: int = 0


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    freq: dict[str, int] = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    n = len(s)
    return -sum((v / n) * math.log2(v / n) for v in freq.values())


def _levenshtein(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if not s2:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
        prev = curr
    return prev[-1]


def _normalize_homoglyphs(s: str) -> str:
    nfkd = unicodedata.normalize('NFKD', s.lower())
    return ''.join(_HOMOGLYPHS.get(c, c) for c in nfkd)


def _has_homoglyphs(s: str) -> bool:
    return any(c in _HOMOGLYPHS for c in s)


class HeuristicsEngine:
    def __init__(self, config: HeuristicsDefaults) -> None:
        self.config = config
        self._suspicious_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in config.suspicious_username_patterns
        ]

    def evaluate_join(
        self,
        *,
        user_id: int,
        guild_id: int,
        account_created_at: int,
        username: str,
        global_name: str | None = None,
        has_avatar: bool,
        avatar_is_animated: bool = False,
        avatar_hash: str | None = None,
        public_flags: frozenset[str] = frozenset(),
        member_flags: frozenset[str] = frozenset(),
        premium_since: int | None = None,
        invite_code: str | None = None,
        invite_creator_history_count: int = 0,
        recent_join_count: int = 0,
        recent_same_avatar_count: int = 0,
        staff_usernames: list[str] | None = None,
        existing_modlog_count: int = 0,
        kicked_for_verification: bool = False,
        network_prior_flag_count: int = 0,
        network_trusted: bool = False,
    ) -> HeuristicsResult:
        signals: list[SignalFiring] = []
        now = int(time.time())
        w = self.config.weights
        t = self.config.thresholds

        # ── Account age ────────────────────────────────────────────────────────
        age_seconds = now - account_created_at
        age_days = age_seconds / 86400

        if age_seconds < 3600:
            signals.append(SignalFiring(
                "account_age_under_1h", w.account_age_under_1h,
                f"Account created {age_seconds // 60:.0f} minutes ago"))
        elif age_days < 1:
            signals.append(SignalFiring(
                "account_age_under_1d", w.account_age_under_1d,
                f"Account created {age_seconds / 3600:.1f} hours ago"))
        elif age_days < 7:
            signals.append(SignalFiring(
                "account_age_under_7d", w.account_age_under_7d,
                f"Account created {age_days:.0f} days ago"))
        elif age_days < 30:
            signals.append(SignalFiring(
                "account_age_under_30d", w.account_age_under_30d,
                f"Account created {age_days:.0f} days ago"))
        elif age_days < 90:
            signals.append(SignalFiring(
                "account_age_under_90d", w.account_age_under_90d,
                f"Account created {age_days:.0f} days ago"))

        # Positive age signals fire independently (an account can be both >2y and >5y)
        if age_days >= 365 * 2:
            signals.append(SignalFiring(
                "account_age_over_2y", w.account_age_over_2y,
                f"Account is {age_days / 365:.1f} years old (established)"))
        if age_days >= 365 * 5:
            signals.append(SignalFiring(
                "account_age_over_5y", w.account_age_over_5y,
                f"Account is {age_days / 365:.1f} years old (very established)"))

        # ── Avatar / profile ───────────────────────────────────────────────────
        if not has_avatar:
            signals.append(SignalFiring(
                "default_avatar", w.default_avatar, "Using default avatar"))
        elif avatar_is_animated:
            signals.append(SignalFiring(
                "animated_avatar", w.animated_avatar,
                "Animated avatar (requires Nitro — real person)"))

        if not global_name:
            signals.append(SignalFiring(
                "no_global_name", w.no_global_name, "No display name set"))

        # ── Username ───────────────────────────────────────────────────────────
        entropy = _shannon_entropy(username)
        logging.debug(f"[heuristics] username entropy for {username!r} = {entropy:.2f}")
        if entropy >= t.username_entropy_min:
            signals.append(SignalFiring(
                "username_high_entropy", w.username_high_entropy,
                f"Username entropy {entropy:.2f} (≥ {t.username_entropy_min})"))

        if len(username) <= t.username_very_short_max_len:
            signals.append(SignalFiring(
                "username_very_short", w.username_very_short,
                f"Username is only {len(username)} character(s)"))

        if len(username) > 0:
            digit_ratio = sum(c.isdigit() for c in username) / len(username)
            if digit_ratio >= t.username_numbers_ratio:
                signals.append(SignalFiring(
                    "username_many_numbers", w.username_many_numbers,
                    f"Username is {digit_ratio:.0%} digits"))

        for pat in self._suspicious_patterns:
            if pat.search(username):
                signals.append(SignalFiring(
                    "username_suspicious_pattern", w.username_suspicious_pattern,
                    "Username matches known bot-name pattern"))
                break

        # ── Impersonation ──────────────────────────────────────────────────────
        if _has_homoglyphs(username):
            signals.append(SignalFiring(
                "homoglyph_detected", w.homoglyph_detected,
                "Username contains Unicode lookalike characters"))

        if staff_usernames:
            lower_username = username.lower()
            norm_username = _normalize_homoglyphs(username)
            for staff_name in staff_usernames:
                if lower_username == staff_name.lower():
                    continue
                if _levenshtein(norm_username, _normalize_homoglyphs(staff_name)) <= t.staff_impersonation_distance:
                    signals.append(SignalFiring(
                        "impersonation_staff", w.impersonation_staff,
                        f'Username closely resembles staff member "{staff_name}"'))
                    break

        # ── Discord-level flags — suspicious ───────────────────────────────────
        if 'spammer' in public_flags:
            signals.append(SignalFiring(
                "discord_spammer_flag", w.discord_spammer_flag,
                "Discord's Trust & Safety has flagged this account as a spammer"))

        if 'automod_quarantined_username' in member_flags:
            signals.append(SignalFiring(
                "automod_quarantined_username", w.automod_quarantined_username,
                "Discord's AutoMod has quarantined this username"))

        # ── Discord-level flags — trust indicators ─────────────────────────────
        if 'staff' in public_flags:
            signals.append(SignalFiring(
                "discord_staff", w.discord_staff,
                "Verified Discord employee"))

        if 'partner' in public_flags:
            signals.append(SignalFiring(
                "discord_partner", w.discord_partner,
                "Verified Discord Partner"))

        if any(f in public_flags for f in (
            'hypesquad', 'hypesquad_bravery', 'hypesquad_brilliance', 'hypesquad_balance'
        )):
            signals.append(SignalFiring(
                "hypesquad_member", w.hypesquad_member,
                "HypeSquad member (completed interactive quiz)"))

        if 'bug_hunter_level_2' in public_flags:
            signals.append(SignalFiring(
                "bug_hunter_level_2", w.bug_hunter_level_2,
                "Discord Bug Hunter Level 2"))
        elif 'bug_hunter' in public_flags:
            signals.append(SignalFiring(
                "bug_hunter", w.bug_hunter,
                "Discord Bug Hunter Level 1"))

        if 'discord_certified_moderator' in public_flags:
            signals.append(SignalFiring(
                "discord_certified_moderator", w.discord_certified_moderator,
                "Discord Certified Moderator"))

        if 'early_supporter' in public_flags:
            signals.append(SignalFiring(
                "early_supporter", w.early_supporter,
                "Early Nitro Supporter (pre-October 2018)"))

        if any(f in public_flags for f in (
            'early_verified_bot_developer', 'verified_bot_developer'
        )):
            signals.append(SignalFiring(
                "early_bot_developer", w.early_bot_developer,
                "Early verified bot developer"))

        if 'active_developer' in public_flags:
            signals.append(SignalFiring(
                "active_developer", w.active_developer,
                "Has the Active Developer badge (maintains a public bot)"))

        # ── Server membership ──────────────────────────────────────────────────
        if premium_since is not None:
            signals.append(SignalFiring(
                "is_server_booster", w.is_server_booster,
                "Actively boosting this server (requires paid Nitro)"))

        if 'bypasses_verification' in member_flags:
            signals.append(SignalFiring(
                "bypasses_verification", w.bypasses_verification,
                "Bypasses guild verification (phone/MFA verified)"))

        if 'completed_onboarding' in member_flags:
            signals.append(SignalFiring(
                "completed_onboarding", w.completed_onboarding,
                "Completed guild onboarding flow"))

        if 'did_rejoin' in member_flags:
            signals.append(SignalFiring(
                "did_rejoin", w.did_rejoin,
                "Previously left or was removed from this server"))

        if 'started_onboarding' in member_flags and 'completed_onboarding' not in member_flags:
            signals.append(SignalFiring(
                "started_onboarding", w.started_onboarding,
                "Started but did not complete guild onboarding"))

        if 'automod_quarantined_guild_tag' in member_flags:
            signals.append(SignalFiring(
                "automod_quarantined_guild_tag", w.automod_quarantined_guild_tag,
                "Discord's AutoMod has quarantined this member's guild tag"))

        if 'guest' in member_flags:
            signals.append(SignalFiring(
                "guest", w.guest,
                "Temporary guest account (joined via event/activity link)"))

        # ── Join context ───────────────────────────────────────────────────────
        if recent_join_count >= t.join_cluster_min_count:
            signals.append(SignalFiring(
                "join_cluster", w.join_cluster,
                f"{recent_join_count} accounts joined in the last "
                f"{t.join_cluster_window_seconds // 60} min"))

        if avatar_hash and recent_same_avatar_count >= t.avatar_hash_cluster_min_count:
            signals.append(SignalFiring(
                "avatar_hash_cluster", w.avatar_hash_cluster,
                f"{recent_same_avatar_count + 1} recent joiners share the same avatar"))

        if invite_creator_history_count > 0:
            signals.append(SignalFiring(
                "known_bad_invite_creator", w.known_bad_invite_creator,
                f"Invite creator has {invite_creator_history_count} modlog entries"))

        # ── Prior history ──────────────────────────────────────────────────────
        if existing_modlog_count > 0:
            signals.append(SignalFiring(
                "existing_modlog", w.existing_modlog,
                f"Has {existing_modlog_count} existing modlog entries in this server"))

        if kicked_for_verification:
            signals.append(SignalFiring(
                "rejoin_after_verification", w.rejoin_after_verification,
                "Rejoined after verification kick (strong human signal)"))

        # ── Network cross-server reputation ────────────────────────────────────
        if network_prior_flag_count > 0:
            signals.append(SignalFiring(
                "network_prior_flag", w.network_prior_flag,
                f"Flagged suspicious {network_prior_flag_count}× across network servers"))

        if network_trusted:
            signals.append(SignalFiring(
                "network_trusted", w.network_trusted,
                "Member in good standing in another server in this network"))

        score = max(0, min(100, sum(s.score_delta for s in signals)))
        logging.debug(
            f"[engine] evaluate_join user={user_id} guild={guild_id} "
            f"score={score}/100 signals={len(signals)}")
        return HeuristicsResult(
            user_id=user_id, guild_id=guild_id, score=score, signals=signals)

    def evaluate_message(
        self,
        *,
        user_id: int,
        guild_id: int,
        state: PostJoinState,
        content: str,
        channel_id: int,
        mention_count: int,
        role_mention_count: int = 0,
        mention_everyone: bool = False,
        has_links: bool,
        attachment_count: int = 0,
        now: int | None = None,
    ) -> HeuristicsResult:
        if now is None:
            now = int(time.time())

        signals: list[SignalFiring] = []
        w = self.config.weights
        t = self.config.thresholds

        # @everyone / @here is an immediate, severe red flag regardless of score
        if mention_everyone:
            signals.append(SignalFiring(
                "mention_everyone", w.mention_everyone,
                "Used @everyone or @here in an early message"))

        # Multi-channel spam: count unique channels within the time window
        # Include current channel (using `now` as its timestamp for window check)
        unique_channels = len({
            ch_id for ch_id, ts in state.channels_messaged
            if ts >= now - t.multi_channel_window_seconds
        } | {channel_id})
        if unique_channels >= t.multi_channel_min_count:
            signals.append(SignalFiring(
                "multi_channel_spam", w.multi_channel_spam,
                f"Sent messages in {unique_channels} different channels within "
                f"{t.multi_channel_window_seconds // 60} min"))

        if state.first_message_at is not None:
            elapsed = max(1, now - state.first_message_at)
            new_count = state.message_count + 1
            if elapsed <= t.message_rate_window_seconds and new_count > t.message_rate_max:
                signals.append(SignalFiring(
                    "message_rate_high", w.message_rate_high,
                    f"{new_count} messages in {elapsed}s"))

        if has_links and state.message_count < t.link_in_messages_window_count:
            signals.append(SignalFiring(
                "link_in_early_messages", w.link_in_early_messages,
                f"Sent a link in message #{state.message_count + 1}"))

        if mention_count >= t.mention_per_message_max:
            signals.append(SignalFiring(
                "mention_spam", w.mention_spam,
                f"{mention_count} @user mentions in one message"))

        if role_mention_count >= t.role_mention_per_message_max:
            signals.append(SignalFiring(
                "role_mention_spam", w.role_mention_spam,
                f"{role_mention_count} role mentions in one message"))

        if attachment_count >= t.attachment_early_max and state.message_count < t.link_in_messages_window_count:
            signals.append(SignalFiring(
                "attachment_spam", w.attachment_spam,
                f"Sent {attachment_count} attachments in message #{state.message_count + 1}"))

        lower = content.lower()
        for kw in self.config.spam_keywords:
            if kw in lower:
                signals.append(SignalFiring(
                    "keyword_spam", w.keyword_spam,
                    f"Message contains flagged keyword"))
                break

        score = max(0, min(100, sum(s.score_delta for s in signals)))
        return HeuristicsResult(
            user_id=user_id, guild_id=guild_id, score=score, signals=signals)
