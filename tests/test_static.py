from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

import endless_vgm


class MarkupCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.classes: set[str] = set()
        self.elements: dict[str, dict[str, str | None]] = {}

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        self.classes.update((attributes.get("class") or "").split())
        if element_id := attributes.get("id"):
            self.elements[element_id] = {"tag": tag, **attributes}


def player_markup() -> MarkupCollector:
    package_dir = Path(endless_vgm.__file__).parent
    collector = MarkupCollector()
    collector.feed((package_dir / "static" / "index.html").read_text(encoding="utf-8"))
    return collector


def static_asset(name: str) -> str:
    package_dir = Path(endless_vgm.__file__).parent
    return (package_dir / "static" / name).read_text(encoding="utf-8")


def test_player_has_four_panes() -> None:
    markup = player_markup()

    assert {
        "library-panel",
        "album-panel",
        "track-panel",
        "player-panel",
    } <= markup.classes


def test_player_has_keyboard_accessible_panel_resizers() -> None:
    markup = player_markup()

    for element_id in ("playlist-resizer", "album-resizer", "track-resizer"):
        assert markup.elements[element_id]["role"] == "separator"
        assert markup.elements[element_id]["tabindex"] == "0"


def test_player_has_full_track_seek_control() -> None:
    markup = player_markup()
    script = static_asset("app.js")

    assert markup.elements["seek-bar"]["type"] == "range"
    assert markup.elements["loop-seek-bar"]["type"] == "range"
    assert {"current-time", "total-time"} <= markup.elements.keys()
    assert 'elements.loopSeekBar.addEventListener("input", seekLoopAudio)' in script
    assert "candidate.loopEndSeconds" in script


def test_music_refresh_shows_loading_state_and_disables_button() -> None:
    script = static_asset("app.js")
    stylesheet = static_asset("styles.css")

    assert "setLibraryLoading(true)" in script
    assert "setLibraryLoading(false)" in script
    assert "elements.refreshLibrary.disabled = loading" in script
    assert '"読み込み中"' in script
    assert ".quiet-button.loading::before" in stylesheet
    assert ".quiet-button:disabled" in stylesheet
    assert "cursor: not-allowed" in stylesheet


def test_playlist_and_album_sort_controls_toggle_title_and_count_order() -> None:
    markup = player_markup()
    script = static_asset("app.js")
    stylesheet = static_asset("styles.css")

    assert {
        "playlist-sort-title",
        "playlist-sort-count",
        "album-sort-title",
        "album-sort-count",
    } <= markup.elements.keys()
    assert 'playlistSort: {key: "title", direction: "asc"}' in script
    assert 'albumSort: {key: "title", direction: "asc"}' in script
    assert 'toggleLibrarySort("playlist", "title")' in script
    assert 'toggleLibrarySort("playlist", "count")' in script
    assert 'toggleLibrarySort("album", "title")' in script
    assert 'toggleLibrarySort("album", "count")' in script
    assert "LIBRARY_COLLATOR.compare" in script
    assert "playlistSort: state.playlistSort" in script
    assert "albumSort: state.albumSort" in script
    assert ".sort-controls button.active" in stylesheet


def test_playlist_and_album_changes_reset_track_scroll() -> None:
    script = static_asset("app.js")

    assert script.count("elements.trackList.scrollTop = 0") >= 2


def test_refined_loop_candidates_are_primary_and_rank_zero_is_default() -> None:
    markup = player_markup()
    script = static_asset("app.js")

    assert "recommended-candidate-list" in markup.elements
    assert "candidate-count" in markup.elements
    assert "analysis.refinedCandidates" in script
    assert "(candidate) => candidate.rank === 0" in script
    assert "candidate.rank <= 0" in script
    assert "candidate.rank > 0" in script
    assert 'loopMusicEndpointPair: "位置調整"' in script
    assert 'loopAuditioneerFiveSample: "つなぎ目優先"' in script
    assert 'label.textContent = name' in script
    assert "loopAudio.currentTime = 0" in script


def test_selected_track_can_be_reanalyzed_with_loading_state() -> None:
    markup = player_markup()
    script = static_asset("app.js")
    stylesheet = static_asset("styles.css")

    assert markup.elements["reanalyze-track"]["disabled"] is None
    assert 'api(`/api/tracks/${track.id}/reanalyze`' in script
    assert "setReanalyzing(true)" in script
    assert "elements.reanalyzeTrack.disabled = loading" in script
    assert ".reanalyze-button.loading::before" in stylesheet


def test_loop_playback_uses_web_audio_buffer_looping() -> None:
    script = static_asset("app.js")
    loop_player = static_asset("loop-audio-player.js")

    assert 'import {LoopAudioPlayer} from "./loop-audio-player.js"' in script
    assert "monitorLoop" not in script
    assert "createBufferSource()" in loop_player
    assert "source.loop = true" in loop_player
    assert "source.loopStart = this.loopStart" in loop_player
    assert "source.loopEnd = this.loopEnd" in loop_player
    assert "loopAudio.play(true)" in script
    assert "USER_RESUME_TIMEOUT_MS = 3_000" in loop_player


def test_library_selection_and_searches_are_restored_without_autoplay() -> None:
    script = static_asset("app.js")

    assert 'const LIBRARY_STATE_STORAGE_KEY = "endless-vgm-library-state"' in script
    assert "restoreLibraryState();" in script
    assert "playlist: state.currentPlaylist" in script
    assert "albumId: state.currentAlbumId" in script
    assert "trackId: state.currentTrackId" in script
    assert "playlistSearch: elements.playlistSearch.value" in script
    assert "albumSearch: elements.albumSearch.value" in script
    assert "trackSearch: elements.trackSearch.value" in script
    assert "await selectTrack(restoredTrack.id, false, true)" in script
    assert "await playLoop(track, token, false, autoplay)" in script
    assert "if (!shouldPlay)" in script
