"""Tests for database.Collection — get/save/delete/query_one/query_many API."""
import asyncio
import pytest
import sys, pathlib
from unittest.mock import AsyncMock, MagicMock

_loop = asyncio.new_event_loop()
def run(coro):
    return _loop.run_until_complete(coro)

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "kidney-bot"))

from utils.database import Collection, Schemas


def make_collection(primary_key="guild_id", schema_class=None, docs=None, legacy_pk=None):
    """Return a Collection wired to a mock pymongo collection."""
    mongo_col = MagicMock()
    mongo_col.find_one = AsyncMock(return_value=None)
    mongo_col.replace_one = AsyncMock()
    mongo_col.insert_one = AsyncMock()
    mongo_col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    mongo_col.count_documents = AsyncMock(return_value=0)

    cursor = MagicMock()
    cursor.limit = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=docs or [])
    mongo_col.find = MagicMock(return_value=cursor)

    schema = schema_class or Schemas.AutoModSettings
    return Collection(mongo_col, primary_key=primary_key, schema_class=schema, legacy_pk=legacy_pk)


@pytest.fixture
def col():
    return make_collection()


# ── get ───────────────────────────────────────────────────────────────────────

class TestGet:
    def test_cache_miss_hits_mongo(self, col):
        doc = {"guild_id": 1, "log_channel": 100}
        col.collection.find_one = AsyncMock(return_value=doc)
        result = run(col.get(1))
        assert isinstance(result, Schemas.AutoModSettings)
        assert result.log_channel == 100
        col.collection.find_one.assert_called_once()

    def test_cache_hit_skips_mongo(self, col):
        doc = {"guild_id": 1, "log_channel": 100}
        col.cache.add(doc)
        result = run(col.get(1))
        assert result.guild_id == 1
        col.collection.find_one.assert_not_called()

    def test_mongo_none_returns_none(self, col):
        col.collection.find_one = AsyncMock(return_value=None)
        assert run(col.get(99)) is None

    def test_result_cached(self, col):
        doc = {"guild_id": 2}
        col.collection.find_one = AsyncMock(return_value=doc)
        run(col.get(2))
        assert col.cache.get_one({"guild_id": 2}) == doc

    def test_extra_filters_bypass_cache(self):
        col = make_collection(primary_key="user_id", schema_class=Schemas.WarnSchema)
        doc = {"user_id": 7, "guild_id": 8, "warns": []}
        col.collection.find_one = AsyncMock(return_value=doc)
        col.cache.add(doc)
        run(col.get(7, guild_id=8))
        col.collection.find_one.assert_called_once()


# ── all ───────────────────────────────────────────────────────────────────────

class TestAll:
    def test_returns_schema_objects(self):
        docs = [{"guild_id": i, "log_channel": i * 10} for i in range(3)]
        col = make_collection(docs=docs)
        col.collection.find.return_value.to_list = AsyncMock(return_value=docs)
        results = run(col.all())
        assert len(results) == 3
        assert all(isinstance(r, Schemas.AutoModSettings) for r in results)

    def test_limit_applied(self, col):
        run(col.all(limit=50))
        col.collection.find.return_value.limit.assert_called_once_with(50)

    def test_empty_collection(self, col):
        col.collection.find.return_value.to_list = AsyncMock(return_value=[])
        assert run(col.all()) == []


# ── save ──────────────────────────────────────────────────────────────────────

class TestSave:
    def test_insert_when_not_found(self, col):
        col.collection.find_one = AsyncMock(return_value=None)
        schema = Schemas.AutoModSettings(guild_id=5, log_channel=999)
        run(col.save(schema))
        col.collection.insert_one.assert_called_once()
        args = col.collection.insert_one.call_args[0][0]
        assert args["guild_id"] == 5

    def test_replace_when_existing(self, col):
        existing = {"guild_id": 5, "_id": "abc123"}
        col.collection.find_one = AsyncMock(return_value=existing)
        schema = Schemas.AutoModSettings(guild_id=5, log_channel=42)
        run(col.save(schema))
        col.collection.replace_one.assert_called_once()
        filter_arg = col.collection.replace_one.call_args[0][0]
        assert filter_arg == {"_id": "abc123"}

    def test_cache_updated_after_save(self, col):
        col.collection.find_one = AsyncMock(return_value=None)
        schema = Schemas.AutoModSettings(guild_id=10, log_channel=1)
        run(col.save(schema))
        cached = col.cache.get_one({"guild_id": 10})
        assert cached is not None
        assert cached["log_channel"] == 1


# ── delete ────────────────────────────────────────────────────────────────────

class TestDelete:
    def test_mongo_delete_called(self, col):
        run(col.delete(1))
        col.collection.delete_one.assert_called_once_with({"guild_id": 1})

    def test_cache_entry_removed(self, col):
        col.cache.add({"guild_id": 1})
        run(col.delete(1))
        assert col.cache.get_one({"guild_id": 1}) is None

    def test_extra_filters(self):
        col = make_collection(primary_key="user_id", schema_class=Schemas.WarnSchema)
        col.collection.delete_one = AsyncMock(return_value=MagicMock(deleted_count=0))
        run(col.delete(7, guild_id=8))
        assert col.collection.delete_one.call_count == 1


# ── legacy_pk fallback ────────────────────────────────────────────────────────

class TestLegacyPk:
    def test_get_falls_back_to_legacy_field(self):
        col = make_collection(primary_key="user_id", schema_class=Schemas.Currency, legacy_pk="userID")
        legacy_doc = {"userID": "7", "wallet": "1200", "bank": "0"}
        col.collection.find_one = AsyncMock(side_effect=[None, legacy_doc])
        result = run(col.get("7"))
        assert result is not None
        assert result.wallet == 1200
        calls = col.collection.find_one.call_args_list
        assert calls[0][0][0] == {"user_id": "7"}
        assert calls[1][0][0] == {"userID": "7"}

    def test_get_legacy_not_cached_under_new_pk(self):
        col = make_collection(primary_key="user_id", schema_class=Schemas.Currency, legacy_pk="userID")
        legacy_doc = {"userID": "7", "wallet": "100", "bank": "0"}
        col.collection.find_one = AsyncMock(side_effect=[None, legacy_doc])
        run(col.get("7"))
        assert col.cache.get_one({"user_id": "7"}) is None

    def test_save_migrates_legacy_doc(self):
        col = make_collection(primary_key="user_id", schema_class=Schemas.Currency, legacy_pk="userID")
        legacy_doc = {"_id": "abc", "userID": "7", "wallet": "1200", "bank": "0"}
        col.collection.find_one = AsyncMock(side_effect=[None, legacy_doc])
        schema = Schemas.Currency(user_id="7", wallet=1200, bank=0)
        run(col.save(schema))
        col.collection.replace_one.assert_called_once_with({"_id": "abc"}, schema.to_dict())
        col.collection.insert_one.assert_not_called()

    def test_delete_falls_back_to_legacy_field(self):
        col = make_collection(primary_key="user_id", schema_class=Schemas.Currency, legacy_pk="userID")
        col.collection.delete_one = AsyncMock(side_effect=[
            MagicMock(deleted_count=0),
            MagicMock(deleted_count=1),
        ])
        run(col.delete("7"))
        assert col.collection.delete_one.call_count == 2
        assert col.collection.delete_one.call_args_list[1][0][0] == {"userID": "7"}


# ── query_one / query_many ────────────────────────────────────────────────────

class TestQueryEscapeHatches:
    def test_query_one_returns_schema(self):
        col = make_collection(primary_key="user_id", schema_class=Schemas.WarnSchema)
        doc = {"user_id": 5, "guild_id": 6, "warns": [{"id": "abc"}]}
        col.collection.find_one = AsyncMock(return_value=doc)
        result = run(col.query_one({"warns.id": "abc"}))
        assert isinstance(result, Schemas.WarnSchema)
        assert result.user_id == 5

    def test_query_one_none_when_not_found(self, col):
        col.collection.find_one = AsyncMock(return_value=None)
        assert run(col.query_one({"complex": "filter"})) is None

    def test_query_many_returns_list_of_schemas(self):
        docs = [{"user_id": i, "announce_level": 3} for i in range(5)]
        col = make_collection(primary_key="user_id", schema_class=Schemas.UserConfig, docs=docs)
        col.collection.find.return_value.to_list = AsyncMock(return_value=docs)
        results = run(col.query_many({"announce_level": {"$gte": 3}}))
        assert len(results) == 5
        assert all(isinstance(r, Schemas.UserConfig) for r in results)

    def test_query_many_empty_result(self, col):
        col.collection.find.return_value.to_list = AsyncMock(return_value=[])
        results = run(col.query_many({"x": 1}))
        assert results == []


# ── exists / count ────────────────────────────────────────────────────────────

class TestExistsCount:
    def test_exists_true_when_found(self, col):
        col.collection.find_one = AsyncMock(return_value={"guild_id": 1})
        assert run(col.exists(1)) is True

    def test_exists_false_when_not_found(self, col):
        col.collection.find_one = AsyncMock(return_value=None)
        assert run(col.exists(99)) is False

    def test_count_calls_mongo(self, col):
        col.collection.count_documents = AsyncMock(return_value=7)
        result = run(col.count())
        assert result == 7
