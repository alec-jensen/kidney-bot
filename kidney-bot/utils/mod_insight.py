# Moderation insight engine — pure logic, no Discord imports.
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

from __future__ import annotations

import time
from dataclasses import dataclass, field

SECONDS_IN_DAY = 86400


@dataclass
class SuggestedAction:
    action_type: str
    duration: str | None = None  # e.g. "4h" — only meaningful for tempmute

    def label(self) -> str:
        if self.action_type == "tempmute" and self.duration:
            return f"{self.duration} Timeout"
        return self.action_type.capitalize()


@dataclass
class EscalationRule:
    id: str
    action_types: list[str]
    min_count: int
    window_days: int
    suggestions: list[SuggestedAction]

    @classmethod
    def from_dict(cls, d: dict) -> EscalationRule:
        cond = d.get("conditions", {})
        return cls(
            id=d["id"],
            action_types=cond.get("action_types", []),
            min_count=cond.get("min_count", 1),
            window_days=cond.get("window_days", 7),
            suggestions=[
                SuggestedAction(s["action_type"], s.get("duration"))
                for s in d.get("suggestions", [])
            ],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "conditions": {
                "action_types": self.action_types,
                "min_count": self.min_count,
                "window_days": self.window_days,
            },
            "suggestions": [
                {"action_type": s.action_type, **({"duration": s.duration} if s.duration else {})}
                for s in self.suggestions
            ],
        }


DEFAULT_RULES: list[EscalationRule] = [
    EscalationRule(
        id="warn_3_7d",
        action_types=["warn"],
        min_count=3,
        window_days=7,
        suggestions=[SuggestedAction("tempmute", "4h"), SuggestedAction("kick")],
    ),
    EscalationRule(
        id="warn_5_7d",
        action_types=["warn"],
        min_count=5,
        window_days=7,
        suggestions=[SuggestedAction("kick"), SuggestedAction("ban")],
    ),
    EscalationRule(
        id="kick_2_30d",
        action_types=["kick"],
        min_count=2,
        window_days=30,
        suggestions=[SuggestedAction("ban")],
    ),
]

_ACTION_ORDER = ["warn", "tempmute", "mute", "kick", "ban"]


@dataclass
class HistorySummary:
    counts_7d: dict[str, int] = field(default_factory=dict)
    counts_all: dict[str, int] = field(default_factory=dict)

    def count_7d(self, action_type: str) -> int:
        return self.counts_7d.get(action_type, 0)

    def count_all(self, action_type: str) -> int:
        return self.counts_all.get(action_type, 0)

    def total_7d(self) -> int:
        return sum(self.counts_7d.values())

    def describe(self) -> str:
        parts: list[str] = []
        seen: set[str] = set()
        for at in _ACTION_ORDER:
            count = self.counts_7d.get(at, 0)
            if count > 0:
                parts.append(f"{count} {at}{'s' if count != 1 else ''}")
            seen.add(at)
        for at, count in self.counts_7d.items():
            if at not in seen and count > 0:
                parts.append(f"{count} {at}{'s' if count != 1 else ''}")
        if not parts:
            return "no actions in the last 7 days"
        return ", ".join(parts) + " in the last 7 days"


@dataclass
class InsightResult:
    summary: HistorySummary
    matched_rule: EscalationRule | None
    suggestions: list[SuggestedAction]
    has_notable_history: bool


def _build_summary(history: list, window_seconds: int) -> HistorySummary:
    cutoff = int(time.time()) - window_seconds
    counts_7d: dict[str, int] = {}
    counts_all: dict[str, int] = {}
    for entry in history:
        ts = entry.timestamp or 0
        at = entry.action_type or "unknown"
        counts_all[at] = counts_all.get(at, 0) + 1
        if ts >= cutoff:
            counts_7d[at] = counts_7d.get(at, 0) + 1
    return HistorySummary(counts_7d=counts_7d, counts_all=counts_all)


def analyze(history: list, guild_rules: list[dict] | None = None) -> InsightResult:
    """Evaluate escalation rules and return an InsightResult.

    Rules are evaluated in order; the last matching rule wins (highest severity).
    """
    summary = _build_summary(history, 7 * SECONDS_IN_DAY)

    rules = [EscalationRule.from_dict(r) for r in guild_rules] if guild_rules else DEFAULT_RULES

    matched: EscalationRule | None = None
    for rule in rules:
        rule_cutoff = int(time.time()) - rule.window_days * SECONDS_IN_DAY
        count = sum(
            1 for e in history
            if (e.timestamp or 0) >= rule_cutoff and e.action_type in rule.action_types
        )
        if count >= rule.min_count:
            matched = rule  # later match overwrites — most severe rule wins

    return InsightResult(
        summary=summary,
        matched_rule=matched,
        suggestions=matched.suggestions if matched else [],
        has_notable_history=summary.total_7d() > 1 or matched is not None,
    )
