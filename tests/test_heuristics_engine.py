"""Tests for utils.heuristics_engine — pure scoring logic (no Discord/DB)."""
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "kidney-bot"))

from utils.heuristics_config import DEFAULTS, ActionConfig
from utils.heuristics_engine import HeuristicsEngine, PostJoinState


def make_engine():
    return HeuristicsEngine(DEFAULTS)


# ── Bug report repro: brand-new account that immediately spams ────────────────

class TestBrandNewAccountSpamRepro:
    """
    Regression coverage for the reported bug: a brand-new account (default
    avatar, no other suspicious profile signals) joins and immediately spams
    across multiple channels. The join-time score alone must NOT cross the
    alert threshold (that's working as designed — profile signals alone are
    intentionally soft) but the join score + behavioral score COMBINED must
    comfortably cross it, proving the engine's math supports detection once a
    JoinTrack exists to carry the behavioral signals.
    """

    def test_join_time_score_alone_is_under_alert_threshold(self):
        engine = make_engine()
        result = engine.evaluate_join(
            user_id=1, guild_id=1,
            account_created_at=int(time.time()) - 60,  # 1 minute old
            username="normaluser",
            global_name="Normal User",
            has_avatar=False,  # default avatar
        )
        # age_under_1h (+25) + default_avatar (+8) = 33, under alert_threshold (40)
        assert result.score < DEFAULTS.actions.alert_threshold
        assert result.score == 33

    def test_behavioral_spam_score_is_high_on_its_own(self):
        engine = make_engine()
        state = PostJoinState(message_count=0, channels_messaged=[], first_message_at=None,
                               total_mentions=0)
        now = 1_000_000
        # First message establishes first_message_at; simulate rapid multi-channel spam
        # by pretending prior messages already landed in two other channels seconds ago.
        state = PostJoinState(
            message_count=5,
            channels_messaged=[(111, now - 2), (222, now - 1)],
            first_message_at=now - 5,
            total_mentions=0,
        )
        msg_result = engine.evaluate_message(
            user_id=1, guild_id=1, state=state,
            content="check this out",
            channel_id=333,
            mention_count=0,
            has_links=False,
            now=now,
        )
        signal_ids = {s.signal_id for s in msg_result.signals}
        assert "multi_channel_spam" in signal_ids
        assert "message_rate_high" in signal_ids
        assert msg_result.score > 0

    def test_combined_join_plus_behavioral_crosses_alert_threshold(self):
        """
        This is the crux of the bug: join score (33) alone doesn't alert, but
        join score + behavioral score together comfortably does — which is why
        on_message() must be able to run (i.e. a JoinTrack must exist) for
        every new join, not just ones that already scored high at join time.
        """
        engine = make_engine()
        join_result = engine.evaluate_join(
            user_id=1, guild_id=1,
            account_created_at=int(time.time()) - 60,
            username="normaluser",
            global_name="Normal User",
            has_avatar=False,
        )
        now = 1_000_000
        state = PostJoinState(
            message_count=5,
            channels_messaged=[(111, now - 2), (222, now - 1)],
            first_message_at=now - 5,
            total_mentions=0,
        )
        msg_result = engine.evaluate_message(
            user_id=1, guild_id=1, state=state,
            content="check this out",
            channel_id=333,
            mention_count=0,
            has_links=False,
            now=now,
        )
        combined = min(100, join_result.score + msg_result.score)
        assert combined >= DEFAULTS.actions.alert_threshold


# ── Username entropy near-miss noted in the bug report ─────────────────────────

class TestUsernameEntropyNearMiss:
    def test_oifhqoi3hj1r5_is_just_under_entropy_threshold(self):
        """
        The specific username from the bug report ("oifhqoi3hj1r5") has entropy
        ~3.24, just under the 3.3 threshold, so username_high_entropy correctly
        does not fire for it. This is expected tuning behavior, not a bug.
        """
        engine = make_engine()
        result = engine.evaluate_join(
            user_id=1, guild_id=1,
            account_created_at=int(time.time()) - 60,
            username="oifhqoi3hj1r5",
            global_name=None,
            has_avatar=False,
        )
        signal_ids = {s.signal_id for s in result.signals}
        assert "username_high_entropy" not in signal_ids

    def test_sdlikvnh20oiirr_crosses_entropy_threshold(self):
        engine = make_engine()
        result = engine.evaluate_join(
            user_id=1, guild_id=1,
            account_created_at=int(time.time()) - 60,
            username="sdlikvnh20oiirr",
            global_name=None,
            has_avatar=False,
        )
        signal_ids = {s.signal_id for s in result.signals}
        assert "username_high_entropy" in signal_ids


# ── Default action thresholds ───────────────────────────────────────────────────

class TestDefaultActionThresholds:
    """Guards against re-introducing stale default claims (see heuristics.py TODOs)."""

    def test_defaults_match_documented_values(self):
        actions = ActionConfig()
        assert actions.alert_threshold == 40
        assert actions.mute_threshold == 101
        assert actions.kick_threshold == 101
        assert actions.ban_threshold == 101
        assert actions.rejoin_kick_threshold == 50
        assert actions.rejoin_verify_enabled is False
        assert actions.tracking_days == 7

    def test_mute_kick_ban_are_effectively_disabled_by_default(self):
        """Score is clamped to 100, so a threshold of 101 can never fire."""
        actions = ActionConfig()
        assert actions.mute_threshold > 100
        assert actions.kick_threshold > 100
        assert actions.ban_threshold > 100
