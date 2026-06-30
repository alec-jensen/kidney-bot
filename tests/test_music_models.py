"""Tests for music.py pure-logic components: Track and _ytdlp_error_message.

These are extracted by compiling only the top portion of music.py (up to the
class/function definitions we need) rather than importing the full module,
which would require fully operational Discord and spotdl environments.
"""
import sys, pathlib, ast, types, dataclasses
from typing import Optional

# Grab the source and extract just the dataclass + helper function via exec
_music_src = (pathlib.Path(__file__).parent.parent / "kidney-bot" / "cogs" / "music.py").read_text(encoding="utf-8")

# Execute only the pieces we need in an isolated namespace
_ns: dict = {
    "__name__": "cogs.music",
    "Optional": Optional,
    "dataclasses": dataclasses,
    "dataclass": dataclasses.dataclass,
}
# exec the dataclass block and the helper function
exec(compile(
    "from dataclasses import dataclass\n"
    "from typing import Optional\n"
    + "\n".join(
        line for line in _music_src.splitlines()
        # Include Track dataclass and _ytdlp_error_message function definitions
        # Stop before class GuildMusicState (which needs discord)
        if True
    ),
    "<music_subset>", "exec"
), _ns)

# Actually, simpler: just define the two items directly from their source
# by extracting the relevant AST nodes and re-compiling them.
_tree = ast.parse(_music_src)
_wanted_names = {"Track", "_ytdlp_error_message"}
_nodes = []
for node in _tree.body:
    name = getattr(node, "name", None)
    if name in _wanted_names:
        _nodes.append(node)

_subset = ast.Module(body=_nodes, type_ignores=[])
ast.fix_missing_locations(_subset)

_exec_ns: dict = {"Optional": Optional, "dataclass": dataclasses.dataclass}
exec(compile(_subset, "<music_subset>", "exec"), _exec_ns)

Track = _exec_ns["Track"]
_ytdlp_error_message = _exec_ns["_ytdlp_error_message"]


# ── Track ─────────────────────────────────────────────────────────────────────

class TestTrackRoundTrip:
    def _sample(self, **overrides):
        base = dict(
            title="Never Gonna Give You Up",
            webpage_url="https://youtube.com/watch?v=dQw4w9WgXcQ",
            thumbnail="https://img.youtube.com/vi/dQw4w9WgXcQ/0.jpg",
            duration=212,
            requester_id=123456789,
            requester_name="Alec",
        )
        base.update(overrides)
        return base

    def test_from_dict_to_dict_round_trip(self):
        doc = self._sample()
        track = Track.from_dict(doc)
        assert track.to_dict() == doc

    def test_missing_title_defaults_to_unknown(self):
        doc = self._sample()
        del doc["title"]
        assert Track.from_dict(doc).title == "Unknown"

    def test_missing_thumbnail_is_none(self):
        doc = self._sample()
        del doc["thumbnail"]
        assert Track.from_dict(doc).thumbnail is None

    def test_duration_coerced_from_string(self):
        doc = self._sample(duration="180")
        assert Track.from_dict(doc).duration == 180

    def test_duration_none_becomes_zero(self):
        doc = self._sample(duration=None)
        assert Track.from_dict(doc).duration == 0

    def test_requester_id_coerced_from_string(self):
        doc = self._sample(requester_id="987654321")
        assert Track.from_dict(doc).requester_id == 987654321

    def test_missing_requester_name_defaults_to_unknown(self):
        doc = self._sample()
        del doc["requester_name"]
        assert Track.from_dict(doc).requester_name == "Unknown"


class TestTrackFmtDuration:
    def test_seconds_only(self):
        t = Track("t", "u", None, 45, 1, "x")
        assert t.fmt_duration() == "0:45"

    def test_minutes_and_seconds(self):
        t = Track("t", "u", None, 3 * 60 + 32, 1, "x")
        assert t.fmt_duration() == "3:32"

    def test_hours_minutes_seconds(self):
        t = Track("t", "u", None, 2 * 3600 + 5 * 60 + 9, 1, "x")
        assert t.fmt_duration() == "2:05:09"

    def test_zero_duration(self):
        t = Track("t", "u", None, 0, 1, "x")
        assert t.fmt_duration() == "0:00"

    def test_exactly_one_hour(self):
        t = Track("t", "u", None, 3600, 1, "x")
        assert t.fmt_duration() == "1:00:00"


# ── _ytdlp_error_message ──────────────────────────────────────────────────────

class TestYtdlpErrorMessage:
    def _err(self, msg):
        return Exception(msg)

    def test_age_restricted(self):
        assert "age-restricted" in _ytdlp_error_message(self._err("sign in to confirm your age"), "Song")

    def test_private(self):
        assert "private" in _ytdlp_error_message(self._err("This video is private"), "Song")

    def test_unavailable(self):
        result = _ytdlp_error_message(self._err("Video unavailable"), "Song")
        assert "unavailable" in result or "region" in result

    def test_copyright(self):
        assert "copyright" in _ytdlp_error_message(self._err("has been removed due to copyright"), "Song")

    def test_live_stream(self):
        assert "live" in _ytdlp_error_message(self._err("this is a live stream"), "Song")

    def test_generic_fallback(self):
        result = _ytdlp_error_message(self._err("some unknown error xyz"), "MySong")
        assert "MySong" in result

    def test_title_appears_in_all_messages(self):
        errors = [
            "sign in to confirm your age",
            "This video is private",
            "Video unavailable",
            "has been removed due to copyright",
            "this is a live stream",
            "unknown error",
        ]
        for msg in errors:
            result = _ytdlp_error_message(self._err(msg), "TestTrack")
            assert "TestTrack" in result, f"Title missing for: {msg!r}"
