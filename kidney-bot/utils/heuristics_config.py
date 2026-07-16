# Heuristics engine configuration — every weight and threshold in one place.
# Adjust these to tune sensitivity. Comments explain the reasoning behind each value.
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SignalWeights:
    """
    Score deltas for each signal. Positive = more suspicious. Negative = more human.
    All scores are clamped 0–100 after summing.
    """

    # ── Account age (mutually exclusive — only the worst bracket fires) ────────
    # Weights are intentionally soft. A genuine new user who just made a Discord
    # account to join one server is the canonical innocent case — account age alone
    # must never push a score to the alert threshold.

    # Created less than 1 hour ago.
    account_age_under_1h: int = 25

    # Created less than 1 day ago.
    account_age_under_1d: int = 15

    # Created less than 1 week ago.
    account_age_under_7d: int = 10

    # Created less than 30 days ago.
    account_age_under_30d: int = 5

    # Created less than 90 days ago.
    account_age_under_90d: int = 3

    # Established account (≥ 2 years).
    account_age_over_2y: int = -10

    # Very old account (≥ 5 years).
    account_age_over_5y: int = -20

    # ── Avatar / profile ───────────────────────────────────────────────────────
    # Profile-only signals must never cross the alert threshold without other
    # context. These are soft contributors, not triggers.

    # Using Discord's procedurally generated default avatar.
    default_avatar: int = 8

    # Animated (GIF) avatar requires an active Nitro subscription.
    animated_avatar: int = -20

    # No global display name set (username only).
    no_global_name: int = 3

    # ── Username analysis ──────────────────────────────────────────────────────

    # High Shannon entropy (≥ threshold) indicates a random-looking, likely
    # programmatically generated name (e.g. "x7gk2mqs").
    username_high_entropy: int = 10

    # High digit ratio (username_numbers_ratio).
    username_many_numbers: int = 7

    # Very short username (username_very_short_max_len).
    username_very_short: int = -5

    # Matches a known bot-name regex (e.g. word+4digits, "officialDiscord",
    # "freenitro", etc.).
    username_suspicious_pattern: int = 15

    # ── Impersonation ──────────────────────────────────────────────────────────

    # Username is within edit distance 2 of a staff member's name (after
    # homoglyph normalization).
    impersonation_staff: int = 40

    # Username contains Unicode characters that visually resemble ASCII letters
    # (e.g. Cyrillic "а" instead of Latin "a").
    homoglyph_detected: int = 30

    # ── Discord-level flags — positive (Discord flagged this account) ──────────

    # Discord's Trust & Safety system has flagged this account as a probable
    # spammer.
    discord_spammer_flag: int = 80

    # Discord's AutoMod has quarantined the username because it matched
    # their internal abuse patterns.
    automod_quarantined_username: int = 40

    # ── Discord-level flags — negative (Discord has verified/trusted this account)

    # Active Discord employee.
    discord_staff: int = -100

    # Verified Discord Partner — a server owner or admin with a formal relationship
    # with Discord.
    discord_partner: int = -80

    # Member of a HypeSquad house (Bravery, Brilliance, or Balance).
    hypesquad_member: int = -15

    # Discord Bug Hunter (Level 1).
    bug_hunter: int = -20

    # Discord Bug Hunter Level 2.
    bug_hunter_level_2: int = -30

    # Completed Discord's Moderator Academy program and certification.
    discord_certified_moderator: int = -50

    # Had a Nitro subscription before October 10, 2018.
    early_supporter: int = -60

    # Had a verified bot during Discord's early verified-bot program.
    early_bot_developer: int = -60

    # Has the Active Developer badge (maintains a public bot application).
    active_developer: int = -15

    # ── Server membership signals ──────────────────────────────────────────────

    # Currently boosting this specific guild.
    is_server_booster: int = -50

    # The account has bypassed guild verification requirements (e.g. via phone
    # number verification or MFA).
    bypasses_verification: int = -20

    # Completed the guild's member onboarding flow.
    completed_onboarding: int = -5

    # Previously left or was removed from this server (did_rejoin Discord member flag).
    did_rejoin: int = 5

    # Started but did not complete guild onboarding.
    started_onboarding: int = 5

    # Discord's AutoMod has quarantined this member's guild tag.
    automod_quarantined_guild_tag: int = 35

    # Temporary guest account (joined via event/activity link with limited access).
    guest: int = 15

    # ── Join context ───────────────────────────────────────────────────────────

    # N or more accounts joined within a short window (default: 5 in 5 min).
    join_cluster: int = 20

    # Multiple recent joiners share the same avatar image hash.
    avatar_hash_cluster: int = 40

    # The invite was created by someone who already has modlog entries in this
    # server.
    known_bad_invite_creator: int = 10

    # ── Prior history ──────────────────────────────────────────────────────────

    # Already has modlog entries in this guild.
    existing_modlog: int = 15

    # Rejoined after being kicked specifically for verification.
    rejoin_after_verification: int = -30

    # ── Post-join behavioral signals ───────────────────────────────────────────

    # Sent messages in 3+ different channels within the multi_channel_window_seconds window.
    multi_channel_spam: int = 40

    # Sent more than N messages within a short window.
    message_rate_high: int = 25

    # Sent a link in their first few messages. Primary delivery mechanism for
    # phishing bots and advertisement bots.
    link_in_early_messages: int = 15

    # Used @everyone or @here. Any bot doing this is an immediate, severe threat
    # regardless of other signals.
    mention_everyone: int = 45

    # Many @user mentions in a single message (≥ threshold). Common technique
    # for spam bots trying to maximise reach per message.
    mention_spam: int = 20

    # Multiple role mentions in a single message. Used by bots targeting
    # subscribed-role groups (e.g. game ping roles).
    role_mention_spam: int = 15

    # Many attachments posted in early messages. Some bots spam image/file content
    # to advertise or to overwhelm moderation.
    attachment_spam: int = 20

    # Message contains a known scam or spam keyword (e.g. "free nitro", "steam
    # gift"). High precision when combined with other behavioural signals.
    keyword_spam: int = 30

    # ── Network cross-server reputation ────────────────────────────────────────

    # User has been flagged as suspicious in other servers within the same network.
    # Each prior flag count adds suspicion — repeat offenders across multiple servers
    # are a strong signal of coordinated bot activity.
    network_prior_flag: int = 25

    # User is in confirmed good standing in another network server — member for
    # tracking_days+ with zero modlog entries. Strong negative signal.
    network_trusted: int = -20


@dataclass
class SignalThresholds:
    """Cutoff values that determine when a signal fires."""

    # Shannon entropy minimum for `username_high_entropy`. Entropy of ~3.5 separates
    # meaningfully random strings from typical human-chosen names.
    username_entropy_min: float = 3.3

    # Digit ratio for `username_many_numbers`.
    username_numbers_ratio: float = 0.6

    # Maximum username length for `username_very_short`.
    username_very_short_max_len: int = 4

    # Window for counting recent joins (seconds). 5 minutes captures a rapid wave
    # while ignoring organic traffic spikes that span hours.
    join_cluster_window_seconds: int = 300

    # Minimum joins in the cluster window to fire `join_cluster`. 5 simultaneous
    # joins is unusual enough to be suspicious; lower is prone to false positives.
    join_cluster_min_count: int = 5

    # Minimum same-avatar joiners within the cluster window to fire
    # `avatar_hash_cluster`. 2 is already near-certain for a bot wave.
    avatar_hash_cluster_min_count: int = 2

    # Window for measuring message rate (seconds).
    message_rate_window_seconds: int = 10

    # Maximum messages in the rate window before `message_rate_high` fires.
    message_rate_max: int = 5

    # Window for measuring channel spread (seconds).
    multi_channel_window_seconds: int = 10

    # Minimum unique channels to fire `multi_channel_spam`.
    multi_channel_min_count: int = 3

    # Minimum @user mentions per message to fire `mention_spam`.
    mention_per_message_max: int = 5

    # Minimum role mentions per message to fire `role_mention_spam`.
    role_mention_per_message_max: int = 2

    # Minimum attachments in early messages to fire `attachment_spam`.
    attachment_early_max: int = 3

    # Maximum message index (0-based) within which a link triggers
    # `link_in_early_messages`.
    link_in_messages_window_count: int = 3

    # Maximum Levenshtein edit distance (after homoglyph normalization) for
    # `impersonation_staff`. 2 allows transpositions and single substitutions.
    staff_impersonation_distance: int = 2


@dataclass
class ActionConfig:
    """Score thresholds that trigger automated actions."""

    # Send an alert to the configured channel. Calibrated so that profile signals
    # alone (new account, default avatar, no name) cannot reach this — a cluster
    # signal, behavioral action, or high-confidence flag must also be present.
    alert_threshold: int = 40

    # Timeout the member for 24 hours. Disabled by default (101 never fires);
    # lower this threshold to enable auto-mute, e.g. mute_threshold=55.
    mute_threshold: int = 101

    # Kick the member. Disabled by default; lower to enable, e.g. kick_threshold=70.
    kick_threshold: int = 101

    # Ban the member immediately. Disabled by default; lower to enable, e.g. ban_threshold=85.
    ban_threshold: int = 101

    # Kick with a "rejoin to verify" DM. Fires below kick_threshold — the idea is
    # that a human will rejoin (dropping their score via rejoin_after_verification)
    # while a bot won't bother. Set higher than alert so a solo suspicious profile
    # can trigger staff visibility but not an automatic action.
    rejoin_kick_threshold: int = 50

    # Whether rejoin-to-verify kicking is enabled. Disabled by default; must be
    # explicitly enabled by the server owner.
    rejoin_verify_enabled: bool = False

    # How long (hours) after a verification kick to watch for a rejoin.
    rejoin_verify_window_hours: int = 24

    # How many days to monitor a new member's behaviour after joining.
    tracking_days: int = 7


@dataclass
class HeuristicsDefaults:
    weights: SignalWeights = field(default_factory=SignalWeights)
    thresholds: SignalThresholds = field(default_factory=SignalThresholds)
    actions: ActionConfig = field(default_factory=ActionConfig)

    # Regex patterns that fire `username_suspicious_pattern` when matched against
    # the username (case-insensitive). Add patterns here as new bot name formats
    # are observed in the wild.
    suspicious_username_patterns: list[str] = field(default_factory=lambda: [
        r'^[a-z]{4,8}\d{4}$',          # word + exactly 4 digits (extremely common bot pattern)
        r'discord\.gg/',                 # invite link embedded in the name
        r'nitro.{0,5}free',             # "nitro free", "nitrofree", etc.
        r'free.{0,5}nitro',
        r'steam.{0,5}gift',             # Steam gift card scams
        r'^bot\d+$',                     # "bot1", "bot123", etc.
        r'official.{0,10}discord',      # impersonating Discord
        r'discord.{0,10}official',
        r'admin.{0,5}\d+$',             # "admin1234" pattern
        r'^[a-z0-9]{20,}$',             # all-lowercase alphanumeric, 20+ chars (generated)
    ])

    # Substrings checked (case-insensitive) against message content to fire
    # `keyword_spam`. Add new scam phrases as they emerge.
    spam_keywords: list[str] = field(default_factory=lambda: [
        'free nitro',
        'discord nitro',
        'gift card',
        'steam gift',
        'click here',
        'limited time',
        'claim now',
        'verify your account',
        'airdrop',
        'crypto giveaway',
        'nft giveaway',
    ])


DEFAULTS = HeuristicsDefaults()
