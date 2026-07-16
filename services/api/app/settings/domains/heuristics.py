from __future__ import annotations

from utils.database import Schemas
from utils.heuristics_config import DEFAULTS

from app.settings.types import DomainSpec, FieldDescriptor, simple_domain

_load, _save = simple_domain("heuristics_config", Schemas.GuildHeuristicsConfig)

# ── Core (top-level GuildHeuristicsConfig fields) ──────────────────────────────

CORE_FIELDS: list[FieldDescriptor] = [
    FieldDescriptor(
        "enabled", "bool", "Enabled", "Turns the heuristics engine on for this server. Off by default.", default=False
    ),
    FieldDescriptor(
        "tracking_days",
        "int",
        "Tracking window (days)",
        "How many days to monitor a new member's behaviour after joining.",
        default=DEFAULTS.actions.tracking_days,
        min=1,
        max=90,
    ),
    FieldDescriptor(
        "alert_channel_id", "channel", "Alert channel", "Channel that receives auto-action alerts.", default=None
    ),
    FieldDescriptor(
        "review_channel_id",
        "channel",
        "Review channel",
        "Channel that receives the mod review queue for borderline scores.",
        default=None,
    ),
    FieldDescriptor(
        "auto_delete_on_ban",
        "bool",
        "Auto-delete on ban",
        "Automatically delete message history when the engine auto-bans someone.",
        default=False,
    ),
    FieldDescriptor(
        "auto_delete_seconds",
        "int",
        "Auto-delete window (seconds)",
        "How much message history to delete (max 604800 = 7 days).",
        default=86400,
        min=0,
        max=604800,
        depends_on={"field": "auto_delete_on_ban", "value": True},
    ),
    FieldDescriptor(
        "auto_delete_score_threshold",
        "int",
        "Auto-delete score threshold",
        "Only auto-delete if the score is at least this high. Leave unset to apply to all auto-bans.",
        default=None,
        min=0,
        max=100,
        depends_on={"field": "auto_delete_on_ban", "value": True},
    ),
    FieldDescriptor(
        "alert_threshold",
        "int",
        "Alert threshold",
        "Score at which an alert is sent to the alert channel.",
        source="action_overrides",
        default=DEFAULTS.actions.alert_threshold,
        min=0,
        max=100,
    ),
    FieldDescriptor(
        "rejoin_kick_threshold",
        "int",
        "Rejoin-kick threshold",
        "Score at which a member is kicked with a rejoin-to-verify prompt.",
        source="action_overrides",
        default=DEFAULTS.actions.rejoin_kick_threshold,
        min=0,
        max=100,
        depends_on={"field": "rejoin_verify_enabled", "value": True},
    ),
    FieldDescriptor(
        "mute_threshold",
        "int",
        "Mute threshold",
        "Score at which a member is automatically timed out. 101 disables this action.",
        source="action_overrides",
        default=DEFAULTS.actions.mute_threshold,
        min=0,
        max=101,
    ),
    FieldDescriptor(
        "kick_threshold",
        "int",
        "Kick threshold",
        "Score at which a member is automatically kicked. 101 disables this action.",
        source="action_overrides",
        default=DEFAULTS.actions.kick_threshold,
        min=0,
        max=101,
    ),
    FieldDescriptor(
        "ban_threshold",
        "int",
        "Ban threshold",
        "Score at which a member is automatically banned. 101 disables this action.",
        source="action_overrides",
        default=DEFAULTS.actions.ban_threshold,
        min=0,
        max=101,
    ),
    FieldDescriptor(
        "rejoin_verify_enabled",
        "bool",
        "Rejoin-verify enabled",
        "Whether rejoin-to-verify kicking is enabled.",
        source="action_overrides",
        default=DEFAULTS.actions.rejoin_verify_enabled,
    ),
    FieldDescriptor(
        "rejoin_verify_window_hours",
        "int",
        "Rejoin-verify window (hours)",
        "How long after a verification kick to watch for a rejoin.",
        source="action_overrides",
        default=DEFAULTS.actions.rejoin_verify_window_hours,
        min=1,
        max=168,
        depends_on={"field": "rejoin_verify_enabled", "value": True},
    ),
]

HEURISTICS_CORE = DomainSpec(
    key="heuristics",
    label="Heuristics",
    fields=CORE_FIELDS,
    load=_load,
    save=_save,
    description="Anti-bot heuristics engine: enable/disable, alert & review channels, "
    "action thresholds, and auto-delete on ban.",
)

# ── Signal weights (SignalWeights, flattened into weight_overrides) ────────────

_W = DEFAULTS.weights


def _w(name: str, label: str, help_text: str, group: str) -> FieldDescriptor:
    return FieldDescriptor(
        name,
        "int",
        label,
        help_text,
        source="weight_overrides",
        default=getattr(_W, name),
        min=-100,
        max=100,
        group=group,
    )


WEIGHT_FIELDS: list[FieldDescriptor] = [
    # Account age — mutually exclusive brackets, intentionally soft.
    _w("account_age_under_1h", "Account age < 1 hour", "Created less than 1 hour ago.", "Account age"),
    _w("account_age_under_1d", "Account age < 1 day", "Created less than 1 day ago.", "Account age"),
    _w("account_age_under_7d", "Account age < 7 days", "Created less than 1 week ago.", "Account age"),
    _w("account_age_under_30d", "Account age < 30 days", "Created less than 30 days ago.", "Account age"),
    _w("account_age_under_90d", "Account age < 90 days", "Created less than 90 days ago.", "Account age"),
    _w("account_age_over_2y", "Account age > 2 years", "Established account (2+ years old).", "Account age"),
    _w("account_age_over_5y", "Account age > 5 years", "Very old account (5+ years old).", "Account age"),
    # Avatar / profile
    _w(
        "default_avatar", "Default avatar", "Using Discord's procedurally generated default avatar.", "Avatar & profile"
    ),
    _w(
        "animated_avatar",
        "Animated avatar",
        "Animated (GIF) avatar — requires an active Nitro subscription.",
        "Avatar & profile",
    ),
    _w("no_global_name", "No display name", "No global display name set (username only).", "Avatar & profile"),
    # Username analysis
    _w("username_high_entropy", "High-entropy username", "Random-looking, likely generated username.", "Username"),
    _w("username_many_numbers", "Many numbers in username", "High digit ratio in the username.", "Username"),
    _w(
        "username_very_short",
        "Very short username",
        "Username at or under the configured short-name length.",
        "Username",
    ),
    _w(
        "username_suspicious_pattern",
        "Suspicious username pattern",
        "Matches a known bot-name pattern (e.g. word+4digits).",
        "Username",
    ),
    # Impersonation
    _w(
        "impersonation_staff",
        "Impersonating staff",
        "Username is within edit distance of a staff member's name.",
        "Impersonation",
    ),
    _w(
        "homoglyph_detected",
        "Homoglyph characters",
        "Username contains characters that visually resemble ASCII letters.",
        "Impersonation",
    ),
    # Discord flags (positive — Discord flagged this account)
    _w(
        "discord_spammer_flag",
        "Discord spammer flag",
        "Discord's Trust & Safety system has flagged this account.",
        "Discord flags",
    ),
    _w(
        "automod_quarantined_username",
        "AutoMod quarantined username",
        "Discord's AutoMod has quarantined this username.",
        "Discord flags",
    ),
    # Discord flags (negative — Discord trusts this account)
    _w("discord_staff", "Discord staff", "Active Discord employee.", "Discord flags"),
    _w("discord_partner", "Discord partner", "Verified Discord Partner.", "Discord flags"),
    _w("hypesquad_member", "HypeSquad member", "Member of a HypeSquad house.", "Discord flags"),
    _w("bug_hunter", "Bug Hunter", "Discord Bug Hunter (Level 1).", "Discord flags"),
    _w("bug_hunter_level_2", "Bug Hunter Level 2", "Discord Bug Hunter Level 2.", "Discord flags"),
    _w("discord_certified_moderator", "Certified Moderator", "Completed Discord's Moderator Academy.", "Discord flags"),
    _w("early_supporter", "Early supporter", "Had Nitro before October 10, 2018.", "Discord flags"),
    _w(
        "early_bot_developer",
        "Early bot developer",
        "Had a verified bot during Discord's early verified-bot program.",
        "Discord flags",
    ),
    _w("active_developer", "Active developer", "Has the Active Developer badge.", "Discord flags"),
    # Server membership
    _w("is_server_booster", "Server booster", "Currently boosting this server.", "Server membership"),
    _w(
        "bypasses_verification",
        "Bypasses verification",
        "Account has bypassed guild verification requirements.",
        "Server membership",
    ),
    _w(
        "completed_onboarding",
        "Completed onboarding",
        "Completed the guild's member onboarding flow.",
        "Server membership",
    ),
    _w("did_rejoin", "Rejoined server", "Previously left or was removed from this server.", "Server membership"),
    _w(
        "started_onboarding",
        "Started onboarding",
        "Started but did not complete guild onboarding.",
        "Server membership",
    ),
    _w(
        "automod_quarantined_guild_tag",
        "AutoMod quarantined guild tag",
        "Discord's AutoMod has quarantined this member's guild tag.",
        "Server membership",
    ),
    _w("guest", "Guest account", "Temporary guest account (joined via event/activity link).", "Server membership"),
    # Join context
    _w("join_cluster", "Join cluster", "N or more accounts joined within a short window.", "Join context"),
    _w(
        "avatar_hash_cluster",
        "Avatar hash cluster",
        "Multiple recent joiners share the same avatar image hash.",
        "Join context",
    ),
    _w(
        "known_bad_invite_creator",
        "Known bad invite creator",
        "Invite was created by someone with prior modlog entries.",
        "Join context",
    ),
    # Prior history
    _w("existing_modlog", "Existing modlog entries", "Already has modlog entries in this guild.", "Prior history"),
    _w(
        "rejoin_after_verification",
        "Rejoined after verification kick",
        "Rejoined after being kicked specifically for verification.",
        "Prior history",
    ),
    # Post-join behavioral signals
    _w(
        "multi_channel_spam",
        "Multi-channel spam",
        "Sent messages in 3+ different channels within the window.",
        "Behavioral",
    ),
    _w("message_rate_high", "High message rate", "Sent more than N messages within a short window.", "Behavioral"),
    _w("link_in_early_messages", "Link in early messages", "Sent a link in their first few messages.", "Behavioral"),
    _w("mention_everyone", "Used @everyone/@here", "Used @everyone or @here.", "Behavioral"),
    _w("mention_spam", "Mention spam", "Many @user mentions in a single message.", "Behavioral"),
    _w("role_mention_spam", "Role mention spam", "Multiple role mentions in a single message.", "Behavioral"),
    _w("attachment_spam", "Attachment spam", "Many attachments posted in early messages.", "Behavioral"),
    _w("keyword_spam", "Keyword spam", "Message contains a known scam or spam keyword.", "Behavioral"),
    # Network cross-server reputation
    _w(
        "network_prior_flag",
        "Network prior flag",
        "Flagged as suspicious in other servers within the same network.",
        "Network reputation",
    ),
    _w(
        "network_trusted",
        "Network trusted",
        "In confirmed good standing in another network server.",
        "Network reputation",
    ),
]

HEURISTICS_WEIGHTS = DomainSpec(
    key="heuristics_weights",
    label="Heuristics: signal weights",
    fields=WEIGHT_FIELDS,
    load=_load,
    save=_save,
    description="Per-signal score adjustments used by the heuristics engine. Positive = more "
    "suspicious, negative = more human. Overrides the built-in defaults.",
    reset_sources=["weight_overrides"],
)

# ── Signal thresholds (SignalThresholds, flattened into threshold_overrides) ──

_T = DEFAULTS.thresholds


def _t(name: str, type_: str, label: str, help_text: str, **kwargs: object) -> FieldDescriptor:
    return FieldDescriptor(
        name,
        type_,
        label,
        help_text,
        source="threshold_overrides",  # type: ignore[arg-type]
        default=getattr(_T, name),
        **kwargs,
    )  # type: ignore[arg-type]


THRESHOLD_FIELDS: list[FieldDescriptor] = [
    _t(
        "username_entropy_min",
        "float",
        "Username entropy minimum",
        "Shannon entropy above which a username counts as high-entropy.",
        min=0,
        max=8,
    ),
    _t(
        "username_numbers_ratio",
        "float",
        "Username digit ratio",
        "Digit ratio above which a username counts as 'many numbers'.",
        min=0,
        max=1,
    ),
    _t(
        "username_very_short_max_len",
        "int",
        "Very-short username max length",
        "Usernames at or under this length count as very short.",
        min=1,
        max=20,
    ),
    _t(
        "join_cluster_window_seconds",
        "int",
        "Join cluster window (seconds)",
        "Window for counting recent joins.",
        min=10,
        max=3600,
    ),
    _t(
        "join_cluster_min_count",
        "int",
        "Join cluster minimum count",
        "Minimum joins in the window to fire a join cluster signal.",
        min=2,
        max=100,
    ),
    _t(
        "avatar_hash_cluster_min_count",
        "int",
        "Avatar hash cluster minimum count",
        "Minimum same-avatar joiners in the window to fire the signal.",
        min=2,
        max=100,
    ),
    _t(
        "message_rate_window_seconds",
        "int",
        "Message rate window (seconds)",
        "Window for measuring message rate.",
        min=1,
        max=600,
    ),
    _t(
        "message_rate_max",
        "int",
        "Message rate maximum",
        "Maximum messages in the rate window before the signal fires.",
        min=1,
        max=100,
    ),
    _t(
        "multi_channel_window_seconds",
        "int",
        "Multi-channel window (seconds)",
        "Window for measuring channel spread.",
        min=1,
        max=600,
    ),
    _t(
        "multi_channel_min_count",
        "int",
        "Multi-channel minimum count",
        "Minimum unique channels to fire the multi-channel spam signal.",
        min=2,
        max=20,
    ),
    _t(
        "mention_per_message_max",
        "int",
        "Mentions per message maximum",
        "Minimum @user mentions per message to fire mention spam.",
        min=1,
        max=50,
    ),
    _t(
        "role_mention_per_message_max",
        "int",
        "Role mentions per message maximum",
        "Minimum role mentions per message to fire role mention spam.",
        min=1,
        max=20,
    ),
    _t(
        "attachment_early_max",
        "int",
        "Early attachments maximum",
        "Minimum attachments in early messages to fire attachment spam.",
        min=1,
        max=20,
    ),
    _t(
        "link_in_messages_window_count",
        "int",
        "Link window message count",
        "Maximum message index within which a link triggers the signal.",
        min=1,
        max=20,
    ),
    _t(
        "staff_impersonation_distance",
        "int",
        "Staff impersonation edit distance",
        "Maximum edit distance (after homoglyph normalization) to count as impersonation.",
        min=0,
        max=10,
    ),
]

HEURISTICS_THRESHOLDS = DomainSpec(
    key="heuristics_thresholds",
    label="Heuristics: signal thresholds",
    fields=THRESHOLD_FIELDS,
    load=_load,
    save=_save,
    description="Cutoff values that determine when a signal fires (windows, minimum counts, "
    "entropy/ratio thresholds). Advanced — the defaults suit most servers.",
    reset_sources=["threshold_overrides"],
)
