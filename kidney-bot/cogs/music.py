# Music cog for KidneyBot
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import asyncio
import enum
import logging
import math
import random
import re
import time
import traceback
from dataclasses import dataclass
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp

from utils.kidney_bot import KidneyBot

from spotdl.utils.spotify import SpotifyClient

log = logging.getLogger(__name__)

_SPOTIFY_TRACK_RE = re.compile(r'open\.spotify\.com/track/([A-Za-z0-9]+)')
_SPOTIFY_PLAYLIST_RE = re.compile(r'open\.spotify\.com/playlist/([A-Za-z0-9]+)')
_SPOTIFY_ALBUM_RE = re.compile(r'open\.spotify\.com/album/([A-Za-z0-9]+)')

PLAYLIST_TRACK_LIMIT = 500
QUEUE_PAGE_SIZE = 10
ALONE_TIMEOUT = 300

_YDL_COMMON = {
    "quiet": True,
    "no_warnings": True,
    "source_address": "0.0.0.0",
}


class LoopMode(enum.Enum):
    OFF = "off"
    TRACK = "track"
    QUEUE = "queue"


@dataclass
class Track:
    title: str
    webpage_url: str  # stable page URL (or ytsearch: query before first play)
    thumbnail: Optional[str]
    duration: int     # seconds; 0 if unknown
    requester_id: int
    requester_name: str

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "webpage_url": self.webpage_url,
            "thumbnail": self.thumbnail,
            "duration": self.duration,
            "requester_id": self.requester_id,
            "requester_name": self.requester_name,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Track":
        return cls(
            title=d.get("title", "Unknown"),
            webpage_url=d["webpage_url"],
            thumbnail=d.get("thumbnail"),
            duration=int(d.get("duration") or 0),
            requester_id=int(d["requester_id"]),
            requester_name=d.get("requester_name", "Unknown"),
        )

    def fmt_duration(self) -> str:
        m, s = divmod(self.duration, 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class GuildMusicState:
    """All per-guild music state, including the player loop."""

    def __init__(self, bot: KidneyBot, guild: discord.Guild):
        self.bot = bot
        self.guild = guild
        self.queue: list[Track] = []
        self.current: Optional[Track] = None
        self.voice_client: Optional[discord.VoiceClient] = None
        self.text_channel: Optional[discord.TextChannel] = None
        self.loop_mode = LoopMode.OFF
        self.volume: float = 0.5

        self._play_next_event = asyncio.Event()
        self._player_task: Optional[asyncio.Task] = None

        self._play_start: float = 0.0
        self._pause_start: float = 0.0
        self._total_paused: float = 0.0
        self._seek_offset: float = 0.0

        # If set, player loop replays current track from this position
        self._seek_position: Optional[float] = None

        self._alone_since: Optional[float] = None
        self._paused_for_alone: bool = False

        # Pre-fetch: resolved stream for queue[0], ready before it's needed
        self._prefetch_task: Optional[asyncio.Task] = None
        self._prefetched: Optional[tuple[Track, str, str]] = None  # (track, stream_url, before_opts)

        # Persistent now-playing panel message
        self._np_message: Optional[discord.Message] = None

        # Set before intentional disconnects so on_voice_state_update won't reconnect
        self._intentional_disconnect: bool = False

        # Injected by Music._state() so the player loop can update the NP panel
        self._cog: Optional["Music"] = None

        log.debug(f"[{guild}] GuildMusicState created")

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def is_playing(self) -> bool:
        return bool(self.voice_client and self.voice_client.is_playing())

    @property
    def is_paused(self) -> bool:
        return bool(self.voice_client and self.voice_client.is_paused())

    @property
    def elapsed(self) -> float:
        if not self._play_start:
            return 0.0
        paused = self._total_paused
        if self.is_paused and self._pause_start:
            paused += time.time() - self._pause_start
        return self._seek_offset + max(0.0, time.time() - self._play_start - paused)

    # ── Playback controls ─────────────────────────────────────────────────────

    def pause(self) -> bool:
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            self._pause_start = time.time()
            log.info(f"[{self.guild}] Paused '{self.current.title if self.current else '?'}' at {self.elapsed:.1f}s")
            return True
        return False

    def resume(self) -> bool:
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
            if self._pause_start:
                self._total_paused += time.time() - self._pause_start
                self._pause_start = 0.0
            log.info(f"[{self.guild}] Resumed '{self.current.title if self.current else '?'}'")
            return True
        return False

    def skip(self):
        log.info(f"[{self.guild}] Skipping '{self.current.title if self.current else '?'}'")
        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            self.voice_client.stop()

    def stop(self, clear_queue: bool = True):
        log.info(f"[{self.guild}] Stop called (clear_queue={clear_queue})")
        if clear_queue:
            self.queue.clear()
        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            self.voice_client.stop()

    def set_volume(self, vol: float):
        old = self.volume
        self.volume = max(0.0, min(1.0, vol))
        log.info(f"[{self.guild}] Volume changed {int(old * 100)}% → {int(self.volume * 100)}%")
        # Restart from current position so the new -filter:a volume= takes effect
        if self.current is not None and (self.is_playing or self.is_paused):
            log.debug(f"[{self.guild}] Restarting track to apply new volume at {self.elapsed:.1f}s")
            self.seek(self.elapsed)

    def shuffle(self):
        log.info(f"[{self.guild}] Queue shuffled ({len(self.queue)} tracks)")
        random.shuffle(self.queue)

    def seek(self, seconds: float) -> bool:
        if self.current is None or not self.voice_client:
            log.warning(f"[{self.guild}] Seek to {seconds:.1f}s called but nothing is playing")
            return False
        log.info(f"[{self.guild}] Seeking '{self.current.title}' to {seconds:.1f}s")
        self._seek_position = seconds
        self.skip()  # _after_play fires → event set → loop replays with -ss
        return True

    # ── Player task ───────────────────────────────────────────────────────────

    def _after_play(self, error: Optional[Exception]):
        if error:
            log.error(f"[{self.guild}] Playback error from FFmpeg: {error}")
        else:
            log.debug(f"[{self.guild}] Track finished cleanly")
        if self._pause_start:
            self._total_paused += time.time() - self._pause_start
            self._pause_start = 0.0
        self.bot.loop.call_soon_threadsafe(self._play_next_event.set)

    async def start_player(self):
        if self._player_task is None or self._player_task.done():
            log.info(f"[{self.guild}] Starting player loop ({len(self.queue)} tracks in queue)")
            self._player_task = asyncio.create_task(
                self._player_loop(), name=f"music-player-{self.guild.id}"
            )

    async def _player_loop(self):
        log.debug(f"[{self.guild}] Player loop entered")
        while True:
            self._play_next_event.clear()

            if self._seek_position is not None:
                track = self.current
                seek_to = self._seek_position
                self._seek_position = None
                log.debug(f"[{self.guild}] Player loop: seek restart to {seek_to:.1f}s for '{track.title if track else '?'}'")
                if track is None:
                    log.warning(f"[{self.guild}] Seek requested but current track is None — exiting loop")
                    return
            else:
                track = self._next_track()
                seek_to = None

            if track is None:
                log.info(f"[{self.guild}] Queue exhausted — player loop exiting")
                self.current = None
                await self._save()
                await self._clear_np_message()
                return

            self.current = track
            log.info(f"[{self.guild}] Next track: '{track.title}' (duration={track.fmt_duration()}, url={track.webpage_url[:80]})")

            # Use pre-fetched stream if it matches the track we're about to play
            if (
                seek_to is None
                and self._prefetched is not None
                and self._prefetched[0] is track
            ):
                stream_url, before_opts = self._prefetched[1], self._prefetched[2]
                self._prefetched = None
                log.info(f"[{self.guild}] Using pre-fetched stream for '{track.title}'")
            else:
                if self._prefetched is not None:
                    log.debug(f"[{self.guild}] Pre-fetched track mismatch — discarding and fetching live")
                self._prefetched = None
                t0 = time.perf_counter()
                log.info(f"[{self.guild}] Fetching stream for '{track.title}' (query: {track.webpage_url[:80]})")
                try:
                    stream_url, before_opts, resolved_url = await self._fetch_stream(
                        track.webpage_url, seek_to
                    )
                    elapsed_fetch = time.perf_counter() - t0
                    log.info(f"[{self.guild}] Stream fetched in {elapsed_fetch:.2f}s for '{track.title}'")
                    # Cache the resolved YouTube URL so searches don't repeat on loop
                    if resolved_url and track.webpage_url.startswith("ytsearch"):
                        log.debug(f"[{self.guild}] Resolved '{track.webpage_url[:60]}' → {resolved_url}")
                        track.webpage_url = resolved_url
                except Exception as e:
                    elapsed_fetch = time.perf_counter() - t0
                    msg = _ytdlp_error_message(e, track.title)
                    log.error(f"[{self.guild}] Stream fetch failed after {elapsed_fetch:.2f}s for '{track.title}': {e}")
                    if self.text_channel:
                        try:
                            await self.text_channel.send(f"⚠️ {msg}, skipping.")
                        except Exception:
                            pass
                    continue

            if not self.voice_client or not self.voice_client.is_connected():
                log.warning(f"[{self.guild}] Voice client disconnected before playback could start — exiting loop")
                break

            self._play_start = time.time()
            self._total_paused = 0.0
            self._pause_start = 0.0
            self._seek_offset = seek_to or 0.0

            log.info(f"[{self.guild}] Starting playback: '{track.title}'" + (f" (seek={seek_to:.1f}s)" if seek_to else ""))
            source = discord.FFmpegOpusAudio(
                stream_url,
                before_options=before_opts,
                options=f'-vn -filter:a "volume={self.volume}"',
            )
            self.voice_client.play(source, after=self._after_play)

            await self._save()

            if seek_to is None:
                await self._update_np()
                self._schedule_prefetch()

            log.debug(f"[{self.guild}] Waiting for '{track.title}' to finish...")
            await self._play_next_event.wait()
            log.debug(f"[{self.guild}] Play-next event fired for '{track.title}'")

    def _next_track(self) -> Optional[Track]:
        if self.loop_mode == LoopMode.TRACK and self.current is not None:
            log.debug(f"[{self.guild}] Loop=TRACK: replaying '{self.current.title}'")
            return self.current
        if self.queue:
            nxt = self.queue.pop(0)
            if self.loop_mode == LoopMode.QUEUE and self.current is not None:
                self.queue.append(self.current)
                log.debug(f"[{self.guild}] Loop=QUEUE: re-appended '{self.current.title}', queue now {len(self.queue)} tracks")
            return nxt
        return None

    # ── Stream fetching ───────────────────────────────────────────────────────

    async def _fetch_stream(
        self, webpage_url: str, seek_to: Optional[float] = None
    ) -> tuple[str, str, Optional[str]]:
        """Returns (audio_stream_url, ffmpeg_before_options, resolved_webpage_url)."""
        def _run():
            opts = {**_YDL_COMMON, "format": "bestaudio/best"}
            with yt_dlp.YoutubeDL(opts) as ydl:
                t0 = time.perf_counter()
                log.debug(f"yt-dlp extracting info for: {webpage_url[:80]}")
                info = ydl.extract_info(webpage_url, download=False)
                log.debug(f"yt-dlp initial extract took {time.perf_counter() - t0:.2f}s")

                if not info:
                    raise RuntimeError("yt-dlp returned no info")

                resolved = None

                # Unwrap search results / playlists to a single video entry
                if info.get("_type") in ("playlist", "multi_video"):
                    entries = list(info.get("entries") or [])
                    log.debug(f"yt-dlp got playlist/search result with {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}")
                    if not entries:
                        raise RuntimeError("No results found for query")
                    info = entries[0]
                    resolved = info.get("webpage_url")
                    log.debug(f"yt-dlp search resolved to: {resolved or '(no webpage_url)'}")

                    # Search entries are sometimes lazily loaded with no formats yet;
                    # re-extract the actual video URL to get the full format list.
                    if not info.get("formats"):
                        video_url = info.get("webpage_url") or info.get("url")
                        if not video_url:
                            raise RuntimeError("Search result entry has no URL")
                        log.debug(f"yt-dlp entry is lazily loaded — re-extracting: {video_url}")
                        t1 = time.perf_counter()
                        info = ydl.extract_info(video_url, download=False)
                        log.debug(f"yt-dlp re-extract took {time.perf_counter() - t1:.2f}s")
                        if not info:
                            raise RuntimeError("Failed to extract video info")

                formats = info.get("formats", [info])
                audio_only = [
                    f for f in formats
                    if f.get("acodec") != "none" and f.get("vcodec") == "none"
                ]
                candidates = audio_only if audio_only else formats
                best = max(candidates, key=lambda f: f.get("tbr") or f.get("abr") or 0)

                log.debug(
                    f"yt-dlp selected format: id={best.get('format_id')} "
                    f"acodec={best.get('acodec')} vcodec={best.get('vcodec')} "
                    f"tbr={best.get('tbr')} abr={best.get('abr')} "
                    f"audio_only_candidates={len(audio_only)}/{len(formats)}"
                )

                stream_url = best.get("url")
                if not stream_url:
                    raise RuntimeError("Selected format has no stream URL")
                return stream_url, resolved

        audio_url, resolved_url = await self.bot.loop.run_in_executor(None, _run)
        reconnect = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
        before_opts = f"-ss {int(seek_to)} {reconnect}" if seek_to is not None else reconnect
        return audio_url, before_opts, resolved_url

    # ── Pre-fetch ─────────────────────────────────────────────────────────────

    def _schedule_prefetch(self):
        if self._prefetch_task and not self._prefetch_task.done():
            self._prefetch_task.cancel()
        self._prefetched = None
        if not self.queue:
            log.debug(f"[{self.guild}] No next track to pre-fetch")
            return
        next_track = self.queue[0]
        duration = self.current.duration if self.current else 0
        delay = max(0.0, float(duration) - 30) if duration else 0.0
        log.info(
            f"[{self.guild}] Scheduling pre-fetch for '{next_track.title}' "
            f"in {delay:.0f}s (current track duration={duration}s)"
        )
        self._prefetch_task = asyncio.create_task(
            self._run_prefetch(delay), name=f"music-prefetch-{self.guild.id}"
        )

    async def _run_prefetch(self, delay: float):
        try:
            if delay > 0:
                log.debug(f"[{self.guild}] Pre-fetch sleeping {delay:.0f}s")
                await asyncio.sleep(delay)
            if not self.queue:
                log.debug(f"[{self.guild}] Pre-fetch woke but queue is now empty — aborting")
                return
            next_track = self.queue[0]
            log.info(f"[{self.guild}] Pre-fetching stream for '{next_track.title}'")
            t0 = time.perf_counter()
            stream_url, before_opts, resolved_url = await self._fetch_stream(next_track.webpage_url)
            elapsed = time.perf_counter() - t0
            if resolved_url and next_track.webpage_url.startswith("ytsearch"):
                log.debug(f"[{self.guild}] Pre-fetch resolved '{next_track.title}' → {resolved_url}")
                next_track.webpage_url = resolved_url
            self._prefetched = (next_track, stream_url, before_opts)
            log.info(f"[{self.guild}] Pre-fetch complete for '{next_track.title}' in {elapsed:.2f}s")
        except asyncio.CancelledError:
            log.debug(f"[{self.guild}] Pre-fetch cancelled")
        except Exception as e:
            log.warning(f"[{self.guild}] Pre-fetch failed: {e}")
            self._prefetched = None

    # ── Now-playing panel ─────────────────────────────────────────────────────

    def now_playing_embed(self) -> discord.Embed:
        track = self.current
        if track is None:
            return discord.Embed(title="Nothing playing", color=discord.Color.greyple())

        elapsed = int(self.elapsed)
        duration = track.duration
        progress = min(elapsed / duration, 1.0) if duration else 0.0
        bar = "▓" * int(20 * progress) + "░" * (20 - int(20 * progress))

        def fmt(s: int) -> str:
            m, sec = divmod(s, 60)
            h, m = divmod(m, 60)
            return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"

        loop_label = {"off": "Off", "track": "🔂 Track", "queue": "🔁 Queue"}[self.loop_mode.value]
        title = "Now Playing" + (" ⏸" if self.is_paused else "")
        is_url = track.webpage_url.startswith("http")
        description = f"[{track.title}]({track.webpage_url})" if is_url else track.title

        embed = discord.Embed(title=title, description=description, color=discord.Color.blurple())
        embed.add_field(
            name="Progress",
            value=f"`{fmt(elapsed)} {bar} {fmt(duration)}`",
            inline=False,
        )
        embed.add_field(name="Requested by", value=f"<@{track.requester_id}>", inline=True)
        embed.add_field(name="Loop", value=loop_label, inline=True)
        embed.add_field(name="Volume", value=f"{int(self.volume * 100)}%", inline=True)

        upcoming = self.queue[:2]
        if upcoming:
            lines = [
                f"`{i + 1}.` {f'[{t.title}]({t.webpage_url})' if t.webpage_url.startswith('http') else t.title} — `{t.fmt_duration()}`"
                for i, t in enumerate(upcoming)
            ]
            embed.add_field(name="Up next", value="\n".join(lines), inline=False)

        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
        return embed

    async def _update_np(self):
        """Delete the old now-playing panel and send a fresh one at the bottom of the channel."""
        if self._cog is None:
            log.debug(f"[{self.guild}] _update_np: no cog reference, skipping")
            return
        if self.text_channel is None:
            log.debug(f"[{self.guild}] _update_np: no text channel set, skipping")
            return

        # Delete the old panel so the new one lands at the bottom
        if self._np_message is not None:
            try:
                await self._np_message.delete()
                log.debug(f"[{self.guild}] Deleted old now-playing panel")
            except discord.NotFound:
                pass
            except Exception as e:
                log.warning(f"[{self.guild}] Could not delete old now-playing panel: {e}")
            self._np_message = None

        embed = self.now_playing_embed()
        view = NowPlayingView(self._cog, self.guild.id)
        try:
            self._np_message = await self.text_channel.send(embed=embed, view=view)
            log.debug(f"[{self.guild}] Now-playing panel sent at bottom of channel")
        except Exception as e:
            log.error(f"[{self.guild}] Failed to send now-playing panel: {e}")

    async def _clear_np_message(self):
        if self._np_message is not None:
            log.debug(f"[{self.guild}] Clearing now-playing panel")
            try:
                await self._np_message.edit(
                    embed=discord.Embed(title="Nothing playing", color=discord.Color.greyple()),
                    view=None,
                )
            except Exception as e:
                log.debug(f"[{self.guild}] Could not clear now-playing panel: {e}")
            self._np_message = None

    # ── Persistence ───────────────────────────────────────────────────────────

    async def _save(self):
        try:
            doc = {
                "guild_id": self.guild.id,
                "voice_channel_id": self.voice_client.channel.id if self.voice_client and self.voice_client.channel else None,
                "text_channel_id": self.text_channel.id if self.text_channel else None,
                "current": self.current.to_dict() if self.current else None,
                "queue": [t.to_dict() for t in self.queue],
                "loop_mode": self.loop_mode.value,
                "volume": self.volume,
            }
            await self.bot.database.music_queues.collection.replace_one(
                {"guild_id": self.guild.id}, doc, upsert=True
            )
            log.debug(f"[{self.guild}] State saved (current='{self.current.title if self.current else None}', queue={len(self.queue)})")
        except Exception as e:
            log.error(f"[{self.guild}] Failed to save music state: {e}")

    async def disconnect(self, save: bool = False):
        log.info(f"[{self.guild}] Disconnecting (save={save})")
        self._intentional_disconnect = True

        if self._prefetch_task and not self._prefetch_task.done():
            log.debug(f"[{self.guild}] Cancelling pre-fetch task")
            self._prefetch_task.cancel()
        if self._player_task and not self._player_task.done():
            log.debug(f"[{self.guild}] Cancelling player task")
            self._player_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(self._player_task), timeout=2)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            self._player_task = None

        if save:
            await self._save()

        self.stop(clear_queue=True)
        self.current = None

        await self._clear_np_message()

        if self.voice_client and self.voice_client.is_connected():
            try:
                await self.voice_client.disconnect(force=True)
                log.info(f"[{self.guild}] Voice client disconnected")
            except Exception as e:
                log.warning(f"[{self.guild}] Error disconnecting voice client: {e}")
        self.voice_client = None

        if not save:
            try:
                await self.bot.database.music_queues.collection.delete_one(
                    {"guild_id": self.guild.id}
                )
                log.debug(f"[{self.guild}] Persisted state cleared from DB")
            except Exception as e:
                log.error(f"[{self.guild}] Failed to clear persisted state: {e}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ytdlp_error_message(e: Exception, title: str) -> str:
    msg = str(e).lower()
    if "age" in msg or "sign in" in msg or "login" in msg:
        return f"**{title}** is age-restricted"
    if "private" in msg:
        return f"**{title}** is private"
    if "not available" in msg or "unavailable" in msg:
        return f"**{title}** is unavailable (possibly region-locked)"
    if "copyright" in msg or "has been removed" in msg:
        return f"**{title}** was removed due to a copyright claim"
    if "live" in msg and "stream" in msg:
        return f"**{title}** is a live stream (not supported)"
    return f"Couldn't load **{title}**"


# ── Queue paginator ────────────────────────────────────────────────────────────

class QueueView(discord.ui.View):
    def __init__(self, state: GuildMusicState):
        super().__init__(timeout=120)
        self.state = state
        self.page = 0

    @property
    def _max_page(self) -> int:
        return max(0, math.ceil(len(self.state.queue) / QUEUE_PAGE_SIZE) - 1)

    def build_embed(self) -> discord.Embed:
        s = self.state
        loop_label = {"off": "Off", "track": "🔂 Track", "queue": "🔁 Queue"}[s.loop_mode.value]
        embed = discord.Embed(
            title="Queue",
            description=f"Loop: **{loop_label}** · Volume: **{int(s.volume * 100)}%**",
            color=discord.Color.blurple(),
        )
        if s.current:
            is_url = s.current.webpage_url.startswith("http")
            link = f"[{s.current.title}]({s.current.webpage_url})" if is_url else s.current.title
            embed.add_field(
                name="Now Playing",
                value=f"{link} — `{s.current.fmt_duration()}`",
                inline=False,
            )
        if not s.queue:
            embed.add_field(name="Up next", value="Queue is empty.", inline=False)
        else:
            start = self.page * QUEUE_PAGE_SIZE
            end = min(start + QUEUE_PAGE_SIZE, len(s.queue))
            lines = []
            for i, t in enumerate(s.queue[start:end], start=start):
                is_url = t.webpage_url.startswith("http")
                link = f"[{t.title}]({t.webpage_url})" if is_url else t.title
                lines.append(f"`{i + 1}.` {link} — `{t.fmt_duration()}`")
            embed.add_field(name="Up next", value="\n".join(lines), inline=False)
            embed.set_footer(text=f"Page {self.page + 1}/{self._max_page + 1} · {len(s.queue)} tracks queued")
        return embed

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.page < self._max_page:
            self.page += 1
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


# ── Now-playing panel view ─────────────────────────────────────────────────────

class NowPlayingView(discord.ui.View):
    def __init__(self, cog: "Music", guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        # Reflect current pause state in the button emoji
        state = cog._states.get(guild_id)
        if state and state.is_paused:
            self.pause_resume_btn.emoji = "▶"
            self.pause_resume_btn.style = discord.ButtonStyle.success

    def _state(self) -> Optional[GuildMusicState]:
        return self.cog._states.get(self.guild_id)

    def _in_channel(self, interaction: discord.Interaction) -> bool:
        state = self._state()
        if state is None or state.voice_client is None:
            return False
        if not isinstance(interaction.user, discord.Member) or not interaction.user.voice:
            return False
        return interaction.user.voice.channel == state.voice_client.channel

    @discord.ui.button(emoji="⏸", style=discord.ButtonStyle.secondary)
    async def pause_resume_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not self._in_channel(interaction):
            await interaction.response.send_message("You must be in the same channel.", ephemeral=True)
            return
        state = self._state()
        if state is None:
            await interaction.response.send_message("Not connected.", ephemeral=True)
            return
        if state.is_playing:
            state.pause()
        elif state.is_paused:
            state.resume()
            state._paused_for_alone = False
        embed = state.now_playing_embed()
        new_view = NowPlayingView(self.cog, self.guild_id)
        await interaction.response.edit_message(embed=embed, view=new_view)

    @discord.ui.button(emoji="⏭", style=discord.ButtonStyle.secondary)
    async def skip_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not self._in_channel(interaction):
            await interaction.response.send_message("You must be in the same channel.", ephemeral=True)
            return
        state = self._state()
        if state is None or state.current is None:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        state.skip()
        await interaction.response.defer()

    @discord.ui.button(emoji="⏹", style=discord.ButtonStyle.danger)
    async def stop_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not self._in_channel(interaction):
            await interaction.response.send_message("You must be in the same channel.", ephemeral=True)
            return
        state = self._state()
        if state is None:
            await interaction.response.send_message("Not connected.", ephemeral=True)
            return
        state.stop(clear_queue=True)
        state.current = None
        await state._save()
        state._np_message = None
        embed = discord.Embed(title="Stopped", color=discord.Color.greyple())
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.secondary)
    async def loop_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not self._in_channel(interaction):
            await interaction.response.send_message("You must be in the same channel.", ephemeral=True)
            return
        state = self._state()
        if state is None:
            await interaction.response.send_message("Not connected.", ephemeral=True)
            return
        modes = [LoopMode.OFF, LoopMode.TRACK, LoopMode.QUEUE]
        state.loop_mode = modes[(modes.index(state.loop_mode) + 1) % len(modes)]
        embed = state.now_playing_embed()
        new_view = NowPlayingView(self.cog, self.guild_id)
        await interaction.response.edit_message(embed=embed, view=new_view)

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.secondary)
    async def shuffle_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not self._in_channel(interaction):
            await interaction.response.send_message("You must be in the same channel.", ephemeral=True)
            return
        state = self._state()
        if state is None:
            await interaction.response.send_message("Not connected.", ephemeral=True)
            return
        if not state.queue:
            await interaction.response.send_message("Queue is empty.", ephemeral=True)
            return
        state.shuffle()
        await interaction.response.send_message("Queue shuffled.", ephemeral=True)


# ── Cog ───────────────────────────────────────────────────────────────────────

class Music(commands.Cog):
    def __init__(self, bot: KidneyBot):
        self.bot = bot
        self._states: dict[int, GuildMusicState] = {}
        self._spotify_client: Optional[SpotifyClient] = None
        self._monitor_task: asyncio.Task = asyncio.create_task(self._monitor_loop())

    def _state(self, guild: discord.Guild) -> GuildMusicState:
        if guild.id not in self._states:
            state = GuildMusicState(self.bot, guild)
            state._cog = self
            self._states[guild.id] = state
        return self._states[guild.id]

    async def cog_unload(self):
        log.info("Music cog unloading — disconnecting all guilds")
        self._monitor_task.cancel()
        for state in list(self._states.values()):
            await state.disconnect(save=True)

    @commands.Cog.listener()
    async def on_ready(self):
        log.info("Music cog: initializing spotdl SpotifyClient (use_official_api=False)")
        t0 = time.perf_counter()
        self._spotify_client = SpotifyClient.init(
            client_id="",
            client_secret="",
            use_official_api=False,
            headless=True,
            no_cache=True,
        )
        log.info(f"Music cog: SpotifyClient initialized in {time.perf_counter() - t0:.2f}s — instance: {type(self._spotify_client).__name__}")
        await self._restore_queues()

    # ── Voice disconnect recovery ──────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if not member.bot or member.id != self.bot.user.id:
            return
        # Bot was removed from a channel
        if before.channel is None or after.channel is not None:
            return

        state = self._states.get(member.guild.id)
        if state is None:
            return
        if state._intentional_disconnect:
            log.debug(f"[{member.guild}] Voice state update: intentional disconnect, ignoring")
            state._intentional_disconnect = False
            return

        if state.current is None and not state.queue:
            log.debug(f"[{member.guild}] Voice state update: disconnected but nothing queued, not rejoining")
            return

        log.warning(
            f"[{member.guild}] Unexpectedly disconnected from {before.channel} "
            f"(current='{state.current.title if state.current else None}', queue={len(state.queue)}). "
            f"Attempting to rejoin in 2s..."
        )
        await asyncio.sleep(2)
        try:
            log.debug(f"[{member.guild}] Clearing stale voice session before rejoin")
            await member.guild.change_voice_state(channel=None)
            await asyncio.sleep(0.5)
            state.voice_client = await before.channel.connect(timeout=15)
            log.info(f"[{member.guild}] Rejoined {before.channel}")
            # Re-queue the current track so it replays from the start
            if state.current is not None:
                log.debug(f"[{member.guild}] Re-inserting current track '{state.current.title}' at queue front")
                state.queue.insert(0, state.current)
                state.current = None
            await state.start_player()
        except Exception as e:
            log.error(f"[{member.guild}] Rejoin failed: {e}")
            state.voice_client = None

    # ── Startup restore ────────────────────────────────────────────────────────

    async def _restore_queues(self):
        log.info("Restoring persisted music queues...")
        t0 = time.perf_counter()
        count = 0
        try:
            col = self.bot.database.music_queues.collection
            async for doc in col.find({}):
                await self._restore_one(doc)
                count += 1
        except Exception as e:
            log.error(f"Failed to restore music queues: {e}\n{traceback.format_exc()}")
        log.info(f"Queue restore complete: {count} guild(s) queues loaded in {time.perf_counter() - t0:.2f}s")

    async def _restore_one(self, doc: dict):
        guild_id: int = doc.get("guild_id", 0)
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            log.debug(f"Queue restore: guild {guild_id} not found (bot may have left)")
            return

        vc_id: Optional[int] = doc.get("voice_channel_id")
        tc_id: Optional[int] = doc.get("text_channel_id")
        if vc_id is None:
            log.debug(f"Queue restore [{guild}]: no voice_channel_id in doc, skipping")
            return

        voice_ch = guild.get_channel(vc_id)
        if not isinstance(voice_ch, discord.VoiceChannel):
            log.warning(f"Queue restore [{guild}]: voice channel {vc_id} not found or wrong type")
            return

        state = self._state(guild)
        state.loop_mode = LoopMode(doc.get("loop_mode", "off"))
        state.volume = float(doc.get("volume", 0.5))

        if tc_id:
            ch = guild.get_channel(tc_id)
            if isinstance(ch, discord.TextChannel):
                state.text_channel = ch
            else:
                log.debug(f"Queue restore [{guild}]: text channel {tc_id} not found")

        tracks: list[Track] = []
        if current := doc.get("current"):
            try:
                tracks.append(Track.from_dict(current))
            except Exception as e:
                log.warning(f"Queue restore [{guild}]: failed to deserialize current track: {e}")
        for t in doc.get("queue", []):
            try:
                tracks.append(Track.from_dict(t))
            except Exception as e:
                log.warning(f"Queue restore [{guild}]: failed to deserialize queued track: {e}")

        if not tracks:
            log.debug(f"Queue restore [{guild}]: no tracks found in doc, skipping")
            return

        state.queue = tracks
        log.info(f"Queue restore [{guild}]: {len(tracks)} track(s) loaded — scheduling auto-rejoin in 10s")

        # Delay the voice connect so the gateway is fully settled (DAVE E2EE handshake
        # needs all guild events processed first). Queue is already restored so /resume
        # works immediately if the auto-rejoin fails.
        asyncio.create_task(
            self._rejoin_after_restore(state, guild, voice_ch),
            name=f"restore-rejoin-{guild.id}",
        )

    async def _rejoin_after_restore(
        self, state: "GuildMusicState", guild: discord.Guild, voice_ch: discord.VoiceChannel
    ):
        await asyncio.sleep(10)
        # Skip if something already claimed the voice client (user ran /play etc.)
        if state.voice_client is not None and state.voice_client.is_connected():
            log.info(f"Queue restore [{guild}]: voice already connected, skipping auto-rejoin")
            return
        log.info(f"Queue restore [{guild}]: attempting auto-rejoin #{voice_ch.name}")
        try:
            # Clear any zombie session Discord thinks we have from before the restart
            await guild.change_voice_state(channel=None)
            await asyncio.sleep(0.5)
            t0 = time.perf_counter()
            state.voice_client = await voice_ch.connect(timeout=30)
            log.info(f"Queue restore [{guild}]: auto-rejoin connected in {time.perf_counter() - t0:.2f}s")
            await state.start_player()
        except Exception as e:
            log.error(f"Queue restore [{guild}]: auto-rejoin failed: {e} — queue preserved, use /resume")

    # ── Monitor loop (alone detection) ─────────────────────────────────────────

    async def _monitor_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await asyncio.sleep(30)
                for state in list(self._states.values()):
                    await self._check_alone(state)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Error in music monitor: {e}")

    async def _check_alone(self, state: GuildMusicState):
        vc = state.voice_client
        if vc is None or not vc.is_connected():
            return

        channel = vc.channel
        if not isinstance(channel, discord.VoiceChannel):
            return

        humans = [m for m in channel.members if not m.bot]

        if not humans:
            if vc.is_playing():
                log.info(f"[{state.guild}] Alone in {channel.name} — pausing")
                state.pause()
                state._paused_for_alone = True
            if state._alone_since is None:
                state._alone_since = time.time()
                log.info(f"[{state.guild}] Alone timer started in {channel.name}")
            elif time.time() - state._alone_since >= ALONE_TIMEOUT:
                log.info(f"[{state.guild}] Auto-disconnecting from {channel.name} (alone >{ALONE_TIMEOUT}s)")
                if state.text_channel:
                    try:
                        await state.text_channel.send("Left the voice channel — nobody was listening.")
                    except Exception:
                        pass
                await state.disconnect(save=False)
        else:
            if state._alone_since is not None:
                log.info(f"[{state.guild}] Someone rejoined {channel.name} — resetting alone timer")
            state._alone_since = None
            if state._paused_for_alone and vc.is_paused():
                log.info(f"[{state.guild}] Resuming after alone-pause in {channel.name}")
                state.resume()
                state._paused_for_alone = False

    # ── Spotify helpers ────────────────────────────────────────────────────────

    async def _spotify_tracks_from_url(
        self, url: str, requester: discord.Member
    ) -> list[Track]:
        """Fetch Spotify track metadata via direct batched SpotifyClient API calls
        (no per-song Song object construction) and return ready-to-queue Track objects."""
        def _run() -> list[Track]:
            client = self._spotify_client
            if client is None:
                raise RuntimeError("SpotifyClient is not initialized — was on_ready called?")
            raw: list[tuple[str, list[str], Optional[str], int]] = []  # (name, artists, cover_url, duration_ms)

            if m := _SPOTIFY_TRACK_RE.search(url):
                log.info(f"Spotify: fetching single track {m.group(1)}")
                t0 = time.perf_counter()
                t = client.track(m.group(1))
                log.info(f"Spotify: track fetch took {time.perf_counter() - t0:.2f}s")
                if t:
                    cover = ((t.get("album") or {}).get("images") or [{}])[0].get("url")
                    raw.append((t["name"], [a["name"] for a in t["artists"]], cover, t.get("duration_ms") or 0))

            elif m := _SPOTIFY_PLAYLIST_RE.search(url):
                playlist_id = m.group(1)
                log.info(f"Spotify: fetching playlist {playlist_id}")
                offset = 0
                page = 0
                while len(raw) < PLAYLIST_TRACK_LIMIT:
                    t0 = time.perf_counter()
                    data = client.playlist_items(
                        playlist_id,
                        limit=100,
                        offset=offset,
                        fields="items(track(name,artists(name),duration_ms,album(images))),next",
                    )
                    page_time = time.perf_counter() - t0
                    items = data.get("items") or []
                    log.info(f"Spotify: playlist page {page} ({len(items)} tracks) fetched in {page_time:.2f}s (total so far: {len(raw) + len(items)})")
                    if not items:
                        break
                    for item in items:
                        t = item.get("track")
                        if not t or not t.get("name"):
                            continue
                        cover = ((t.get("album") or {}).get("images") or [{}])[0].get("url")
                        raw.append((t["name"], [a["name"] for a in t.get("artists", [])], cover, t.get("duration_ms") or 0))
                    offset += len(items)
                    page += 1
                    if not data.get("next"):
                        log.debug(f"Spotify: no more playlist pages")
                        break
                log.info(f"Spotify: playlist fetch complete — {len(raw)} tracks in {page} page(s)")

            elif m := _SPOTIFY_ALBUM_RE.search(url):
                album_id = m.group(1)
                log.info(f"Spotify: fetching album {album_id}")
                t0 = time.perf_counter()
                album = client.album(album_id) or {}
                log.info(f"Spotify: album metadata fetched in {time.perf_counter() - t0:.2f}s")
                cover = (album.get("images") or [{}])[0].get("url")
                offset = 0
                page = 0
                while len(raw) < PLAYLIST_TRACK_LIMIT:
                    t0 = time.perf_counter()
                    data = client.album_tracks(album_id, limit=50, offset=offset)
                    page_time = time.perf_counter() - t0
                    items = data.get("items") or []
                    log.info(f"Spotify: album page {page} ({len(items)} tracks) fetched in {page_time:.2f}s")
                    if not items:
                        break
                    for t in items:
                        if not t or not t.get("name"):
                            continue
                        raw.append((t["name"], [a["name"] for a in t.get("artists", [])], cover, t.get("duration_ms") or 0))
                    offset += len(items)
                    page += 1
                    if not data.get("next"):
                        break
                log.info(f"Spotify: album fetch complete — {len(raw)} tracks in {page} page(s)")

            tracks = []
            for name, artists, cover, duration_ms in raw[:PLAYLIST_TRACK_LIMIT]:
                display = f"{name} - {artists[0]}" if artists else name
                query = f"{name} {' '.join(artists)}"
                tracks.append(Track(
                    title=display,
                    webpage_url=f"ytsearch1:{query}",
                    thumbnail=cover,
                    duration=duration_ms // 1000,
                    requester_id=requester.id,
                    requester_name=str(requester),
                ))
            return tracks

        log.info(f"Spotify metadata fetch starting for: {url}")
        t0 = time.perf_counter()
        try:
            tracks = await self.bot.loop.run_in_executor(None, _run)
            log.info(f"Spotify metadata fetch complete: {len(tracks)} tracks in {time.perf_counter() - t0:.2f}s total")
            return tracks
        except Exception as e:
            log.error(f"Spotify lookup failed for {url} after {time.perf_counter() - t0:.2f}s: {e}")
            raise

    # ── yt-dlp helpers ─────────────────────────────────────────────────────────

    async def _resolve(self, query: str, requester: discord.Member) -> list[Track]:
        def _run():
            opts = {**_YDL_COMMON, "format": "bestaudio/best", "extract_flat": "in_playlist"}
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(query, download=False)

        log.info(f"yt-dlp resolving: {query[:80]}")
        t0 = time.perf_counter()
        try:
            info = await self.bot.loop.run_in_executor(None, _run)
        except Exception as e:
            log.error(f"yt-dlp resolve failed for '{query[:80]}' after {time.perf_counter() - t0:.2f}s: {e}")
            return []

        if not info:
            log.warning(f"yt-dlp returned no info for '{query[:80]}'")
            return []

        entries = info.get("entries", [info]) if "entries" in info else [info]
        tracks = []
        for entry in entries:
            if not entry:
                continue
            url = entry.get("webpage_url") or entry.get("url")
            if not url:
                continue
            tracks.append(Track(
                title=entry.get("title") or "Unknown",
                webpage_url=url,
                thumbnail=entry.get("thumbnail"),
                duration=int(entry.get("duration") or 0),
                requester_id=requester.id,
                requester_name=str(requester),
            ))

        log.info(f"yt-dlp resolved {len(tracks)} track(s) in {time.perf_counter() - t0:.2f}s for '{query[:80]}'")
        return tracks

    async def _resolve_search(self, query: str, requester: discord.Member) -> list[Track]:
        return await self._resolve(f"ytsearch1:{query}", requester)

    # ── Interaction guards ─────────────────────────────────────────────────────

    def _pre_check_voice(self, interaction: discord.Interaction) -> Optional[str]:
        if not interaction.guild:
            return "Server only."
        if not isinstance(interaction.user, discord.Member) or not interaction.user.voice or not interaction.user.voice.channel:
            return "You must be in a voice channel."
        return None

    async def _ensure_voice(self, interaction: discord.Interaction) -> Optional[GuildMusicState]:
        assert interaction.guild is not None
        assert isinstance(interaction.user, discord.Member)
        assert interaction.user.voice is not None
        assert interaction.user.voice.channel is not None

        state = self._state(interaction.guild)

        if state.voice_client is None or not state.voice_client.is_connected():
            channel = interaction.user.voice.channel
            log.info(f"[{interaction.guild}] Joining voice channel #{channel.name}")
            try:
                t0 = time.perf_counter()
                # Only send a "leave" frame if we actually have a stale connection —
                # sending it when we're not connected causes a 4006 on the next connect.
                if state.voice_client is not None:
                    await interaction.guild.change_voice_state(channel=None)
                    await asyncio.sleep(0.5)
                state.voice_client = await channel.connect(timeout=15)
                log.info(f"[{interaction.guild}] Voice connect took {time.perf_counter() - t0:.2f}s")
            except Exception as e:
                log.error(f"[{interaction.guild}] Failed to join #{channel.name}: {e}")
                await interaction.followup.send(f"Failed to join your voice channel: {e}", ephemeral=True)
                return None

        if isinstance(interaction.channel, discord.TextChannel):
            state.text_channel = interaction.channel

        return state

    async def _check_same_channel(self, interaction: discord.Interaction) -> Optional[GuildMusicState]:
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return None

        state = self._state(interaction.guild)

        if state.voice_client is None or not state.voice_client.is_connected():
            await interaction.response.send_message("I'm not in a voice channel.", ephemeral=True)
            return None

        if not isinstance(interaction.user, discord.Member) or not interaction.user.voice:
            await interaction.response.send_message("You must be in a voice channel.", ephemeral=True)
            return None

        if interaction.user.voice.channel != state.voice_client.channel:
            await interaction.response.send_message("You must be in the same channel as me.", ephemeral=True)
            return None

        return state

    # ── Commands ──────────────────────────────────────────────────────────────

    @app_commands.command(name="play", description="Play a song — YouTube URL/search or Spotify track/playlist/album.")
    @app_commands.describe(query="YouTube URL, Spotify URL, or search terms")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3, key=lambda i: i.user.id)
    async def play(self, interaction: discord.Interaction, query: str):
        if err := self._pre_check_voice(interaction):
            await interaction.response.send_message(err, ephemeral=True)
            return

        await interaction.response.defer()

        state = await self._ensure_voice(interaction)
        if state is None:
            return

        assert isinstance(interaction.user, discord.Member)
        log.info(f"[{interaction.guild}] /play from {interaction.user}: {query[:80]}")

        tracks: list[Track] = []

        if "spotify.com" in query:
            if not (_SPOTIFY_TRACK_RE.search(query) or _SPOTIFY_PLAYLIST_RE.search(query) or _SPOTIFY_ALBUM_RE.search(query)):
                await interaction.followup.send("Unrecognized Spotify URL.", ephemeral=True)
                return
            try:
                tracks = await self._spotify_tracks_from_url(query, interaction.user)
            except Exception as e:
                await interaction.followup.send(f"Failed to load Spotify URL: {e}", ephemeral=True)
                return
            if not tracks:
                await interaction.followup.send("Could not find any tracks at that Spotify URL.", ephemeral=True)
                return
        elif "youtube.com" in query or "youtu.be" in query:
            tracks = await self._resolve(query, interaction.user)
        else:
            tracks = await self._resolve_search(query, interaction.user)

        if not tracks:
            await interaction.followup.send("Nothing found for that query.", ephemeral=True)
            return

        was_idle = not state.is_playing and not state.is_paused
        state.queue.extend(tracks)
        await state._save()

        if len(tracks) == 1:
            msg = f"{'Now playing' if was_idle else 'Added'} **{tracks[0].title}**."
        else:
            msg = f"Added **{len(tracks)} tracks** to the queue."

        log.info(f"[{interaction.guild}] Queued {len(tracks)} track(s) from /play (was_idle={was_idle})")

        if was_idle:
            await state.start_player()

        await interaction.followup.send(msg)

    @app_commands.command(name="pause", description="Pause playback.")
    @app_commands.guild_only()
    async def pause(self, interaction: discord.Interaction):
        state = await self._check_same_channel(interaction)
        if state is None:
            return
        if state.pause():
            await interaction.response.send_message("Paused.", ephemeral=True)
        else:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)

    @app_commands.command(name="resume", description="Resume playback, or rejoin and start a saved queue.")
    @app_commands.guild_only()
    async def resume(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return

        state = self._state(interaction.guild)

        # Bot is connected — standard pause/resume
        if state.voice_client and state.voice_client.is_connected():
            if not isinstance(interaction.user, discord.Member) or not interaction.user.voice:
                await interaction.response.send_message("You must be in a voice channel.", ephemeral=True)
                return
            if interaction.user.voice.channel != state.voice_client.channel:
                await interaction.response.send_message("You must be in the same channel as me.", ephemeral=True)
                return
            if state.resume():
                state._paused_for_alone = False
                await interaction.response.send_message("Resumed.", ephemeral=True)
            else:
                await interaction.response.send_message("Nothing is paused.", ephemeral=True)
            return

        # Bot is not connected but has a saved queue — join and start
        if state.queue or state.current:
            if err := self._pre_check_voice(interaction):
                await interaction.response.send_message(err, ephemeral=True)
                return
            await interaction.response.defer()
            joined = await self._ensure_voice(interaction)
            if joined is None:
                return
            # Restore current track to front of queue if needed
            if joined.current is not None and not joined.is_playing:
                joined.queue.insert(0, joined.current)
                joined.current = None
            total = len(joined.queue)
            log.info(f"[{interaction.guild}] /resume: starting saved queue ({total} tracks)")
            await joined.start_player()
            await interaction.followup.send(f"Resuming saved queue — **{total}** track{'s' if total != 1 else ''}.")
            return

        await interaction.response.send_message("Nothing to resume.", ephemeral=True)

    @app_commands.command(name="stop", description="Stop playback and clear the queue.")
    @app_commands.guild_only()
    async def stop(self, interaction: discord.Interaction):
        state = await self._check_same_channel(interaction)
        if state is None:
            return
        state.stop(clear_queue=True)
        state.current = None
        await state._save()
        await state._clear_np_message()
        await interaction.response.send_message("Stopped and cleared the queue.")

    @app_commands.command(name="skip", description="Skip the current song.")
    @app_commands.guild_only()
    async def skip(self, interaction: discord.Interaction):
        state = await self._check_same_channel(interaction)
        if state is None:
            return
        if state.current is None:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        state.skip()
        await interaction.response.send_message("Skipped.")

    @app_commands.command(name="leave", description="Disconnect the bot from the voice channel.")
    @app_commands.guild_only()
    async def leave(self, interaction: discord.Interaction):
        state = await self._check_same_channel(interaction)
        if state is None:
            return
        await state.disconnect(save=False)
        await interaction.response.send_message("Disconnected.")

    @app_commands.command(name="queue", description="Show the queue.")
    @app_commands.guild_only()
    async def queue_cmd(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        state = self._state(interaction.guild)
        if state.current is None and not state.queue:
            await interaction.response.send_message("The queue is empty.", ephemeral=True)
            return
        view = QueueView(state)
        await interaction.response.send_message(embed=view.build_embed(), view=view)

    @app_commands.command(name="nowplaying", description="Show what's currently playing.")
    @app_commands.guild_only()
    async def nowplaying(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        state = self._state(interaction.guild)
        if state.current is None:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        await interaction.response.send_message(embed=state.now_playing_embed())

    @app_commands.command(name="remove", description="Remove a song from the queue by position.")
    @app_commands.describe(position="Position in the queue (1-based)")
    @app_commands.guild_only()
    async def remove(self, interaction: discord.Interaction, position: int):
        state = await self._check_same_channel(interaction)
        if state is None:
            return
        if position < 1 or position > len(state.queue):
            await interaction.response.send_message(
                f"Position must be between 1 and {len(state.queue)}.", ephemeral=True
            )
            return
        removed = state.queue.pop(position - 1)
        await state._save()
        log.info(f"[{interaction.guild}] Removed '{removed.title}' from queue (position {position})")
        await interaction.response.send_message(f"Removed **{removed.title}** from the queue.")

    @app_commands.command(name="shuffle", description="Shuffle the queue.")
    @app_commands.guild_only()
    async def shuffle(self, interaction: discord.Interaction):
        state = await self._check_same_channel(interaction)
        if state is None:
            return
        if not state.queue:
            await interaction.response.send_message("The queue is empty.", ephemeral=True)
            return
        state.shuffle()
        await state._save()
        await interaction.response.send_message("Queue shuffled.")

    @app_commands.command(name="loop", description="Cycle loop mode: Off → Track → Queue → Off.")
    @app_commands.guild_only()
    async def loop_cmd(self, interaction: discord.Interaction):
        state = await self._check_same_channel(interaction)
        if state is None:
            return
        modes = [LoopMode.OFF, LoopMode.TRACK, LoopMode.QUEUE]
        state.loop_mode = modes[(modes.index(state.loop_mode) + 1) % len(modes)]
        labels = {LoopMode.OFF: "Off", LoopMode.TRACK: "🔂 Track", LoopMode.QUEUE: "🔁 Queue"}
        log.info(f"[{interaction.guild}] Loop mode set to {state.loop_mode.value} by {interaction.user}")
        await interaction.response.send_message(f"Loop set to **{labels[state.loop_mode]}**.")

    @app_commands.command(name="volume", description="Set the playback volume (0–100).")
    @app_commands.describe(level="Volume from 0 to 100")
    @app_commands.guild_only()
    async def volume_cmd(
        self, interaction: discord.Interaction, level: app_commands.Range[int, 0, 100]
    ):
        state = await self._check_same_channel(interaction)
        if state is None:
            return
        state.set_volume(level / 100)
        await state._save()
        await interaction.response.send_message(f"Volume set to **{level}%**.")

    @app_commands.command(name="seek", description="Seek to a position in the current track.")
    @app_commands.describe(position="Time to seek to: mm:ss, hh:mm:ss, or seconds")
    @app_commands.guild_only()
    async def seek_cmd(self, interaction: discord.Interaction, position: str):
        state = await self._check_same_channel(interaction)
        if state is None:
            return
        if state.current is None:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return

        try:
            parts = [int(p) for p in position.split(":")]
            if len(parts) == 1:
                seconds = float(parts[0])
            elif len(parts) == 2:
                seconds = parts[0] * 60.0 + parts[1]
            elif len(parts) == 3:
                seconds = parts[0] * 3600.0 + parts[1] * 60.0 + parts[2]
            else:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "Invalid position — use `mm:ss`, `hh:mm:ss`, or a number of seconds.", ephemeral=True
            )
            return

        if seconds < 0 or (state.current.duration and seconds > state.current.duration):
            await interaction.response.send_message("Position is out of range.", ephemeral=True)
            return

        await interaction.response.defer()
        ok = state.seek(seconds)
        if ok:
            m, s = divmod(int(seconds), 60)
            await interaction.followup.send(f"Seeked to **{m}:{s:02d}**.")
        else:
            await interaction.followup.send("Seek failed.", ephemeral=True)


async def setup(bot: KidneyBot):
    await bot.add_cog(Music(bot))
