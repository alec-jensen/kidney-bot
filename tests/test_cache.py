"""Tests for utils/cache.py"""
import time
import pytest
from unittest.mock import patch

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "kidney-bot"))

from utils.cache import Cache


@pytest.fixture
def cache():
    return Cache(primary_key="guild_id", ttl=300)


class TestCacheAdd:
    def test_add_and_retrieve(self, cache):
        cache.add({"guild_id": 1, "value": "hello"})
        assert cache.get_one({"guild_id": 1}) == {"guild_id": 1, "value": "hello"}

    def test_add_ignores_doc_without_primary_key(self, cache):
        cache.add({"other_field": 99})
        assert len(cache._store) == 0

    def test_add_overwrites_existing_entry(self, cache):
        cache.add({"guild_id": 1, "value": "old"})
        cache.add({"guild_id": 1, "value": "new"})
        assert cache.get_one({"guild_id": 1})["value"] == "new"

    def test_add_many(self, cache):
        docs = [{"guild_id": i, "name": f"guild{i}"} for i in range(5)]
        cache.add_many(docs)
        for i in range(5):
            assert cache.get_one({"guild_id": i}) is not None


class TestCacheGet:
    def test_miss_returns_none(self, cache):
        assert cache.get_one({"guild_id": 99}) is None

    def test_complex_query_bypasses_cache(self, cache):
        cache.add({"guild_id": 1, "whitelist": [10, 20]})
        # Multi-field query should not be served from cache
        result = cache.get_one({"guild_id": 1, "whitelist": {"$in": [10]}})
        assert result is None

    def test_wrong_pk_bypasses_cache(self, cache):
        cache.add({"guild_id": 1, "data": "x"})
        assert cache.get_one({"user_id": 1}) is None

    def test_expired_entry_returns_none(self, cache):
        cache.add({"guild_id": 1, "data": "x"})
        # Manually backdate the entry
        cache._store[1]["ts"] -= 400
        assert cache.get_one({"guild_id": 1}) is None

    def test_expired_entry_is_evicted(self, cache):
        cache.add({"guild_id": 1, "data": "x"})
        cache._store[1]["ts"] -= 400
        cache.get_one({"guild_id": 1})
        assert 1 not in cache._store


class TestCacheUpdate:
    def test_set_updates_field(self, cache):
        cache.add({"guild_id": 1, "log_channel": 100})
        cache.update({"guild_id": 1}, {"$set": {"log_channel": 200}})
        assert cache.get_one({"guild_id": 1})["log_channel"] == 200

    def test_set_adds_new_field(self, cache):
        cache.add({"guild_id": 1})
        cache.update({"guild_id": 1}, {"$set": {"new_field": "hi"}})
        assert cache.get_one({"guild_id": 1})["new_field"] == "hi"

    def test_unset_removes_field(self, cache):
        cache.add({"guild_id": 1, "temp": "x"})
        cache.update({"guild_id": 1}, {"$unset": {"temp": ""}})
        assert "temp" not in cache.get_one({"guild_id": 1})

    def test_update_miss_is_noop(self, cache):
        cache.update({"guild_id": 99}, {"$set": {"x": 1}})  # should not raise

    def test_original_doc_not_mutated(self, cache):
        doc = {"guild_id": 1, "val": "original"}
        cache.add(doc)
        cache.update({"guild_id": 1}, {"$set": {"val": "updated"}})
        assert doc["val"] == "original"


class TestCacheRemove:
    def test_remove_deletes_entry(self, cache):
        cache.add({"guild_id": 1})
        cache.remove({"guild_id": 1})
        assert cache.get_one({"guild_id": 1}) is None

    def test_remove_miss_is_noop(self, cache):
        cache.remove({"guild_id": 99})  # should not raise

    def test_remove_without_pk_is_noop(self, cache):
        cache.add({"guild_id": 1})
        cache.remove({"other": "field"})
        assert cache.get_one({"guild_id": 1}) is not None


class TestCacheCleanup:
    def test_cleanup_removes_expired(self, cache):
        cache.add({"guild_id": 1})
        cache.add({"guild_id": 2})
        cache._store[1]["ts"] -= 400  # expire guild 1
        removed = cache.cleanup()
        assert removed == 1
        assert cache.get_one({"guild_id": 1}) is None
        assert cache.get_one({"guild_id": 2}) is not None

    def test_cleanup_returns_zero_when_nothing_expired(self, cache):
        cache.add({"guild_id": 1})
        assert cache.cleanup() == 0

    def test_clear_empties_store(self, cache):
        cache.add_many([{"guild_id": i} for i in range(10)])
        cache.clear()
        assert len(cache._store) == 0
