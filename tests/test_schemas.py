"""Tests for database Schemas — round-trip serialization and field coercion."""
import pytest
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "kidney-bot"))

from utils.database import Schemas, convert_except_none, remove_none_values


# ── Helpers ───────────────────────────────────────────────────────────────────

class TestConvertExceptNone:
    def test_none_returns_none(self):
        assert convert_except_none(None, int) is None

    def test_converts_correctly(self):
        assert convert_except_none("42", int) == 42
        assert convert_except_none("3.14", float) == pytest.approx(3.14)
        assert convert_except_none(1, bool) is True

    def test_raises_on_bad_value_by_default(self):
        with pytest.raises(ValueError):
            convert_except_none("abc", int)

    def test_returns_default_on_bad_value_when_error_false(self):
        assert convert_except_none("abc", int, default=-1, error=False) == -1


class TestRemoveNoneValues:
    def test_removes_none(self):
        assert remove_none_values({"a": 1, "b": None, "c": 3}) == {"a": 1, "c": 3}

    def test_empty_dict(self):
        assert remove_none_values({}) == {}

    def test_all_none(self):
        assert remove_none_values({"a": None, "b": None}) == {}

    def test_preserves_falsy_non_none(self):
        assert remove_none_values({"a": 0, "b": False, "c": ""}) == {"a": 0, "b": False, "c": ""}


# ── Schema round-trips ────────────────────────────────────────────────────────

class TestCurrencySchema:
    def test_round_trip(self):
        doc = {"user_id": "123456789", "wallet": 500, "bank": 1000, "inventory": {"apple": 2}}
        obj = Schemas.Currency.from_dict(doc)
        assert obj.user_id == "123456789"
        assert obj.wallet == 500
        assert obj.bank == 1000
        assert obj.inventory == {"apple": 2}
        assert obj.to_dict() == doc

    def test_defaults_on_empty_dict(self):
        obj = Schemas.Currency.from_dict({})
        assert obj.user_id is None
        assert obj.wallet is None
        assert obj.bank is None

    def test_none_data_returns_empty_schema(self):
        obj = Schemas.Currency.from_dict(None)
        assert obj.wallet is None

    def test_wallet_coerced_to_int(self):
        obj = Schemas.Currency.from_dict({"user_id": "1", "wallet": "250", "bank": "0"})
        assert isinstance(obj.wallet, int)
        assert obj.wallet == 250

    def test_to_dict_excludes_none(self):
        obj = Schemas.Currency(user_id="1", wallet=100)
        d = obj.to_dict()
        assert "bank" not in d
        assert d["wallet"] == 100



class TestAutoModSettingsSchema:
    def test_round_trip(self):
        doc = {"guild_id": 222, "log_channel": 999, "whitelist": [1, 2, 3]}
        obj = Schemas.AutoModSettings.from_dict(doc)
        assert obj.guild_id == 222
        assert obj.log_channel == 999
        assert obj.whitelist == [1, 2, 3]

    def test_to_dict_excludes_none(self):
        obj = Schemas.AutoModSettings(guild_id=5)
        d = obj.to_dict()
        assert list(d.keys()) == ["guild_id"]


class TestAutoRoleSettingsSchema:
    def test_round_trip(self):
        doc = {"guild_id": 333, "roles": [{"id": 10, "delay": 60}], "bots_get_roles": False}
        obj = Schemas.AutoRoleSettings.from_dict(doc)
        assert obj.guild_id == 333
        assert obj.bots_get_roles is False

    def test_bots_get_roles_field_name(self):
        obj = Schemas.AutoRoleSettings(guild_id=1, bots_get_roles=True)
        assert "bots_get_roles" in obj.to_dict()
        assert "BotsGetRoles" not in obj.to_dict()


class TestScammerListSchema:
    def test_field_is_user_id(self):
        doc = {"user_id": 42, "time": 1000, "reason": "spam"}
        obj = Schemas.ScammerList.from_dict(doc)
        assert obj.user_id == 42
        assert "user_id" in obj.to_dict()
        assert "user" not in obj.to_dict()

    def test_round_trip(self):
        doc = {"user_id": 99, "time": 12345, "reason": "ban evasion"}
        obj = Schemas.ScammerList.from_dict(doc)
        assert obj.to_dict() == doc


class TestWarnSchema:
    def test_round_trip(self):
        warns = [{"reason": "spam", "timestamp": 1000, "moderator": 5, "id": "abc"}]
        doc = {"user_id": 7, "guild_id": 8, "warns": warns}
        obj = Schemas.WarnSchema.from_dict(doc)
        assert obj.user_id == 7
        assert obj.guild_id == 8
        assert obj.warns == warns
        assert obj.to_dict() == doc


class TestGuildConfigSchema:
    def test_round_trip(self):
        doc = {"guild_id": 1, "ephemeral_moderation_messages": True,
               "ephemeral_setting_overpowers_user_setting": False}
        obj = Schemas.GuildConfig.from_dict(doc)
        assert obj.guild_id == 1
        assert obj.to_dict() == doc


class TestMusicQueueSchema:
    def test_round_trip(self):
        doc = {"guild_id": 1, "voice_channel_id": 2, "text_channel_id": 3,
               "current": {"title": "song"}, "queue": [{"title": "next"}],
               "loop_mode": "off", "volume": 0.8}
        obj = Schemas.MusicQueue.from_dict(doc)
        assert obj.guild_id == 1
        assert obj.queue == [{"title": "next"}]
        assert obj.volume == pytest.approx(0.8)
        d = obj.to_dict()
        assert d["queue"] == [{"title": "next"}]

    def test_empty_queue_preserved(self):
        obj = Schemas.MusicQueue(guild_id=1)
        assert obj.queue == []
        assert "queue" in obj.to_dict()

    def test_currency_legacy_userid(self):
        obj = Schemas.Currency.from_dict({"userID": "42", "wallet": 100})
        assert obj.user_id == "42"
        assert "user_id" in obj.to_dict()

    def test_scammer_list_legacy_user(self):
        obj = Schemas.ScammerList.from_dict({"user": 99, "time": 1000})
        assert obj.user_id == 99
        assert "user_id" in obj.to_dict()


class TestSchemaStrRepr:
    def test_str_includes_class_name(self):
        obj = Schemas.Currency(user_id="1", wallet=100, bank=0)
        assert "Currency" in str(obj)

    def test_iter_yields_key_value_pairs(self):
        obj = Schemas.GuildConfig(guild_id=1)
        pairs = dict(obj)
        assert pairs["guild_id"] == 1
