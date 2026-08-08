from __future__ import annotations

import pytest

from endless_vgm.library import playlist_fingerprint
from endless_vgm.watchdog import LibraryWatchdog


class FakeLibrary:
    """In-memory stand-in for MusicLibrary used by the watchdog.

    ``manifests`` are returned by successive ``read_manifest`` calls; once
    exhausted the last manifest repeats so multi-tick tests stay deterministic.
    """

    def __init__(
        self,
        manifests: list[list[dict[str, object]]],
        *,
        fail_refresh_first: bool = False,
    ) -> None:
        self._manifests = list(manifests)
        self._index = 0
        self.refresh_calls: list[str | None] = []
        self.read_error: Exception | None = None
        self._fail_refresh_first = fail_refresh_first

    def read_manifest(self) -> list[dict[str, object]]:
        if self.read_error is not None:
            raise self.read_error
        if not self._manifests:
            return []
        current = self._manifests[min(self._index, len(self._manifests) - 1)]
        self._index += 1
        return current

    def refresh(self, *, fingerprint: str | None = None, **_: object) -> None:
        self.refresh_calls.append(fingerprint)
        if self._fail_refresh_first:
            self._fail_refresh_first = False
            raise RuntimeError("refresh failed")


def _no_sleep(_: float) -> None:
    return None


def test_default_poll_interval_is_30_minutes() -> None:
    watchdog = LibraryWatchdog(FakeLibrary([[]]))

    assert watchdog._interval == 30 * 60


def test_first_tick_primes_baseline_without_refresh() -> None:
    manifest = [{"id": "P1", "name": "GAME", "tracks": ["T1"]}]
    library = FakeLibrary([manifest])
    watchdog = LibraryWatchdog(library, sleeper=_no_sleep)

    assert watchdog.baseline is None
    watchdog._tick()

    assert watchdog.baseline == playlist_fingerprint(manifest)
    assert library.refresh_calls == []


def test_no_change_does_not_refresh() -> None:
    manifest = [{"id": "P1", "name": "GAME", "tracks": ["T1"]}]
    library = FakeLibrary([manifest, manifest, manifest])
    watchdog = LibraryWatchdog(library, debounce=0.0, sleeper=_no_sleep)

    watchdog._tick()
    watchdog._tick()
    watchdog._tick()

    assert watchdog.baseline == playlist_fingerprint(manifest)
    assert library.refresh_calls == []


@pytest.mark.parametrize(
    "changed",
    [
        pytest.param(
            [{"id": "P1", "name": "GAME", "tracks": ["T1", "T2", "T3"]}], id="add track"
        ),
        pytest.param([{"id": "P1", "name": "GAME", "tracks": ["T1"]}], id="remove track"),
        pytest.param(
            [{"id": "P1", "name": "GAME", "tracks": ["T2", "T1"]}], id="reorder tracks"
        ),
        pytest.param(
            [{"id": "P1", "name": "GAME", "tracks": ["T1", "T9"]}], id="same-count swap"
        ),
        pytest.param(
            [{"id": "P1", "name": "GAME2", "tracks": ["T1", "T2"]}], id="rename playlist"
        ),
        pytest.param(
            [
                {"id": "P1", "name": "GAME", "tracks": ["T1", "T2"]},
                {"id": "P2", "name": "NEW", "tracks": []},
            ],
            id="add playlist",
        ),
        pytest.param([], id="remove playlist"),
    ],
)
def test_structural_change_triggers_refresh(changed: list[dict[str, object]]) -> None:
    base = [{"id": "P1", "name": "GAME", "tracks": ["T1", "T2"]}]
    library = FakeLibrary([base, changed])
    watchdog = LibraryWatchdog(library, debounce=0.0, sleeper=_no_sleep)

    watchdog._tick()
    watchdog._tick()

    assert library.refresh_calls == [playlist_fingerprint(changed)]
    assert watchdog.baseline == playlist_fingerprint(changed)


def test_library_only_changes_are_ignored() -> None:
    # The manifest excludes the all-tracks library, so a change confined to it
    # is invisible: identical user-playlist manifests mean no fingerprint change.
    user_only = [{"id": "P1", "name": "GAME", "tracks": ["T1"]}]
    library = FakeLibrary([user_only, user_only])
    watchdog = LibraryWatchdog(library, debounce=0.0, sleeper=_no_sleep)

    watchdog._tick()
    watchdog._tick()

    assert library.refresh_calls == []


def test_debounce_coalesces_rapid_edits_into_one_refresh() -> None:
    m_initial = [{"id": "P1", "name": "GAME", "tracks": ["T1"]}]
    m_mid = [{"id": "P1", "name": "GAME", "tracks": ["T1", "T2"]}]
    m_final = [{"id": "P1", "name": "GAME", "tracks": ["T1", "T2", "T3"]}]
    library = FakeLibrary([m_initial, m_mid, m_final])
    sleeps: list[float] = []
    watchdog = LibraryWatchdog(library, debounce=1.0, sleeper=sleeps.append)

    watchdog._tick()
    watchdog._tick()

    assert library.refresh_calls == [playlist_fingerprint(m_final)]
    assert sleeps == [1.0]


def test_changes_during_refresh_aggregate_to_single_followup() -> None:
    # refresh runs synchronously within a tick, so several edits that happen
    # "during" a refresh collapse into one follow-up refresh on the next tick:
    # intermediate states are never observed individually.
    m_baseline = [{"id": "P1", "name": "GAME", "tracks": ["T1"]}]
    m_first = [{"id": "P1", "name": "GAME", "tracks": ["T1", "T2"]}]
    m_final = [{"id": "P1", "name": "GAME", "tracks": ["T1", "T2", "T3", "T4"]}]
    library = FakeLibrary([m_baseline, m_first, m_final])
    watchdog = LibraryWatchdog(library, debounce=0.0, sleeper=_no_sleep)

    watchdog._tick()
    watchdog._tick()
    watchdog._tick()

    assert library.refresh_calls == [
        playlist_fingerprint(m_first),
        playlist_fingerprint(m_final),
    ]


def test_manifest_query_failure_keeps_baseline() -> None:
    manifest = [{"id": "P1", "name": "GAME", "tracks": ["T1"]}]
    library = FakeLibrary([manifest])
    watchdog = LibraryWatchdog(library, debounce=0.0, sleeper=_no_sleep)

    watchdog._tick()
    primed = watchdog.baseline

    library.read_error = RuntimeError("Music.app busy")
    watchdog._tick()

    assert watchdog.baseline == primed
    assert library.refresh_calls == []


def test_recovers_after_transient_query_failure() -> None:
    manifest = [{"id": "P1", "name": "GAME", "tracks": ["T1"]}]
    library = FakeLibrary([manifest])
    watchdog = LibraryWatchdog(library, debounce=0.0, sleeper=_no_sleep)

    watchdog._tick()
    library.read_error = RuntimeError("Music.app busy")
    watchdog._tick()

    changed = [{"id": "P1", "name": "GAME", "tracks": ["T1", "T2"]}]
    library.read_error = None
    library._manifests = [changed]
    library._index = 0
    watchdog._tick()

    assert library.refresh_calls == [playlist_fingerprint(changed)]


def test_refresh_failure_keeps_baseline_for_retry() -> None:
    m_baseline = [{"id": "P1", "name": "GAME", "tracks": ["T1"]}]
    m_changed = [{"id": "P1", "name": "GAME", "tracks": ["T1", "T2"]}]
    library = FakeLibrary([m_baseline, m_changed], fail_refresh_first=True)
    watchdog = LibraryWatchdog(library, debounce=0.0, sleeper=_no_sleep)

    watchdog._tick()
    primed = watchdog.baseline
    watchdog._tick()

    assert watchdog.baseline == primed
    assert library.refresh_calls == [playlist_fingerprint(m_changed)]

    watchdog._tick()

    assert watchdog.baseline == playlist_fingerprint(m_changed)
    assert library.refresh_calls == [
        playlist_fingerprint(m_changed),
        playlist_fingerprint(m_changed),
    ]


def test_start_and_stop_control_background_thread() -> None:
    library = FakeLibrary([[]])
    watchdog = LibraryWatchdog(library, interval=0.01, debounce=0.0, sleeper=_no_sleep)

    watchdog.start()
    try:
        assert watchdog.baseline is not None
    finally:
        watchdog.stop()

    assert watchdog._thread is None
