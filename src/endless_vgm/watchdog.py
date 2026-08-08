from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from .library import MusicLibrary, playlist_fingerprint

LOGGER = logging.getLogger(__name__)


class LibraryWatchdog:
    """Polls Music.app user playlists and refreshes the library on change.

    Runs as a daemon thread inside the backend server process. Every ``interval``
    seconds it reads the lightweight playlist manifest, fingerprints it, and
    compares against the baseline established at startup. Only structural changes
    (added/removed/renamed playlists, added/removed/reordered tracks) trigger a
    full ``library.refresh()``; metadata-only edits are intentionally ignored.

    Design notes (see the parent task spec):
    * No refresh at startup: the first successful manifest read primes the
      baseline instead of refreshing.
    * Short debounce coalesces a burst of rapid edits into one refresh.
    * Refresh runs synchronously, so changes made during a refresh collapse into
      at most one follow-up refresh on the next tick.
    * A manifest query failure keeps the baseline untouched (no refresh).
    * Cross-process exclusion and skip-if-already-refreshed live inside
      ``MusicLibrary.refresh`` so manual ``make library`` and this watcher share
      one lock and never duplicate work.
    """

    def __init__(
        self,
        library: MusicLibrary,
        *,
        interval: float = 30 * 60,
        debounce: float = 2.0,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._library = library
        self._interval = interval
        self._debounce = debounce
        self._sleeper = sleeper
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._baseline: str | None = None
        self._read_manifest: Callable[[], list[dict[str, object]]] = library.read_manifest

    @property
    def baseline(self) -> str | None:
        return self._baseline

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="endless-vgm-watchdog",
            daemon=True,
        )
        self._thread.start()
        LOGGER.info(
            "Playlist watchdog started (interval=%.1fs debounce=%.1fs)",
            self._interval,
            self._debounce,
        )

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=self._interval + self._debounce + 5)
            self._thread = None
        LOGGER.info("Playlist watchdog stopped")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._tick()
            # wait() returns immediately once stop() sets the event.
            self._stop_event.wait(self._interval)

    def _tick(self) -> None:
        fingerprint = self._current_fingerprint()
        if fingerprint is None:
            # Query failed: keep the baseline and do nothing this tick.
            return
        if self._baseline is None:
            # First successful read primes the baseline; no startup refresh.
            self._baseline = fingerprint
            LOGGER.info("Playlist watch baseline established")
            return
        if fingerprint == self._baseline:
            return
        # Structural change detected. Wait out the debounce so a burst of rapid
        # edits collapses into a single refresh, then re-read the latest state.
        if self._debounce > 0:
            self._sleeper(self._debounce)
            fingerprint = self._current_fingerprint()
            if fingerprint is None:
                return
        self._refresh(fingerprint)

    def _current_fingerprint(self) -> str | None:
        try:
            return playlist_fingerprint(self._read_manifest())
        except Exception as error:  # noqa: BLE001
            LOGGER.warning("Playlist manifest read failed; keeping baseline: %s", error)
            return None

    def _refresh(self, fingerprint: str) -> None:
        try:
            self._library.refresh(fingerprint=fingerprint)
        except Exception as error:  # noqa: BLE001
            # Refresh failed: leave the baseline so the next tick retries.
            LOGGER.warning("Playlist refresh failed; baseline unchanged: %s", error)
            return
        self._baseline = fingerprint
        LOGGER.info("Playlist watch baseline updated after refresh")
