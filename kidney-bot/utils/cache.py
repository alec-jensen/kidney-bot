import logging
import time


class Cache:
    """
    O(1) document cache keyed on a single primary field.

    Only serves cache hits for simple single-key queries (e.g. {guild_id: 123}).
    Queries with extra filter fields are passed through to the database so the
    cache never returns stale partial matches.

    All methods are synchronous — no asyncio needed for dict operations.
    Call cleanup() periodically (the Database class drives this via one shared task).
    """

    def __init__(self, primary_key: str, ttl: int = 300):
        self._pk = primary_key
        self._ttl = ttl
        # primary_key_value → {"value": doc, "ts": float}
        self._store: dict = {}

    # ── write ──────────────────────────────────────────────────────────────────

    def add(self, doc: dict) -> None:
        key = doc.get(self._pk)
        if key is None:
            return
        self._store[key] = {"value": doc, "ts": time.monotonic()}

    def add_many(self, docs: list[dict]) -> None:
        for doc in docs:
            self.add(doc)

    def update(self, query: dict, update: dict) -> None:
        item = self._get_item(query)
        if item is None:
            return
        doc = item["value"].copy()
        if "$set" in update:
            doc.update(update["$set"])
        if "$unset" in update:
            for k in update["$unset"]:
                doc.pop(k, None)
        pk_val = query[self._pk]
        self._store[pk_val] = {"value": doc, "ts": item["ts"]}

    def remove(self, query: dict) -> None:
        pk_val = query.get(self._pk)
        if pk_val is not None:
            self._store.pop(pk_val, None)

    def clear(self) -> None:
        self._store.clear()

    # ── read ───────────────────────────────────────────────────────────────────

    def get_one(self, query: dict):
        """Return cached doc or None. Only answers simple {pk: val} queries."""
        item = self._get_item(query)
        return item["value"] if item is not None else None

    # ── maintenance ────────────────────────────────────────────────────────────

    def cleanup(self) -> int:
        now = time.monotonic()
        expired = [k for k, v in self._store.items() if now - v["ts"] > self._ttl]
        for k in expired:
            del self._store[k]
        if expired:
            logging.debug(f"Cache({self._pk}): evicted {len(expired)} expired entries")
        return len(expired)

    # ── internal ───────────────────────────────────────────────────────────────

    def _get_item(self, query: dict):
        """Return raw cache item only for simple single-pk queries."""
        if len(query) != 1 or self._pk not in query:
            return None
        pk_val = query[self._pk]
        item = self._store.get(pk_val)
        if item is None:
            return None
        if time.monotonic() - item["ts"] > self._ttl:
            del self._store[pk_val]
            return None
        return item
