from __future__ import annotations

import subprocess
from pathlib import Path

import endless_vgm


def export_script_helpers() -> str:
    package_dir = Path(endless_vgm.__file__).parent
    source = (package_dir / "scripts" / "export_music_library.js").read_text(encoding="utf-8")
    return source.split("function run()", maxsplit=1)[0]


def run_jxa(harness: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", export_script_helpers() + harness],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_library_lookup_continues_after_one_source_fails() -> None:
    completed = run_jxa(
        """
function run() {
  const library = {name: () => "Library"};
  const app = {
    sources: () => [
      {libraryPlaylists: () => { throw new Error("Unavailable source"); }},
      {libraryPlaylists: () => [library]},
    ],
    playlists: () => [],
  };
  return waitForLibraryPlaylist(app).name();
}
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "Library"


def test_library_lookup_falls_back_to_music_special_playlist() -> None:
    completed = run_jxa(
        """
function run() {
  const library = {
    class: () => "playlist",
    specialKind: () => "Music",
    name: () => "ミュージック",
  };
  const app = {
    sources: () => [],
    playlists: () => [library],
  };
  return waitForLibraryPlaylist(app).name();
}
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ミュージック"


def test_music_special_playlist_is_identified_as_library() -> None:
    completed = run_jxa(
        """
function run() {
  const playlist = {
    class: () => "playlist",
    specialKind: () => "Music",
  };
  return String(isLibraryPlaylist(playlist));
}
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "true"


def test_playlist_reuses_library_metadata_for_duplicate_tracks() -> None:
    completed = run_jxa(
        """
function run() {
  let propertyReads = 0;
  let reportedName = "";
  const track = {
    properties: () => {
      propertyReads += 1;
      return {
        name: "Battle",
        artist: "Composer",
        albumArtist: "Composer",
        album: "Album",
        discNumber: 1,
        trackNumber: 2,
        location: null,
      };
    },
  };
  const tracks = [track];
  tracks.properties = () => { throw new Error("No bulk properties"); };
  const library = {tracks: () => tracks};
  library.tracks.properties = () => { throw new Error("No bulk properties"); };
  const cache = new Map();
  const all = parseLibraryPlaylist(
    library,
    tracks,
    ["TRACK-ID"],
    cache,
    (_completed, _total, parsed) => { reportedName = parsed.name; },
  );
  const playlist = {
    tracks: () => { throw new Error("Duplicate metadata was read"); },
  };
  const duplicate = parseCachedPlaylist(
    playlist,
    "GAME",
    ["TRACK-ID", "TRACK-ID"],
    cache,
  );
  return JSON.stringify({
    propertyReads,
    reportedName,
    allNames: all.tracks.map((value) => value.name),
    playlistNames: duplicate.tracks.map((value) => value.name),
  });
}
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == (
        '{"propertyReads":1,"reportedName":"Battle","allNames":["Battle"],'
        '"playlistNames":["Battle","Battle"]}'
    )


def test_progress_reporter_updates_once_per_second_and_can_be_forced() -> None:
    completed = run_jxa(
        """
function run() {
  let now = 1000;
  Date.now = () => now;
  const report = progressReporter();
  report(1, "first");
  now = 1500;
  report(2, "too soon");
  now = 2000;
  report(3.25, "one second later");
  report(100, "forced", true);
  return "";
}
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert "進捗 1.0%: first" in completed.stderr
    assert "too soon" not in completed.stderr
    assert "進捗 3.3%: one second later" in completed.stderr
    assert "進捗 100.0%: forced" in completed.stderr


def test_automation_denial_fails_immediately_with_actionable_error() -> None:
    completed = run_jxa(
        """
function run() {
  const denied = new Error("Not authorized");
  denied.errorNumber = -1743;
  const app = {
    sources: () => { throw denied; },
    playlists: () => [],
  };
  return waitForLibraryPlaylist(app);
}
"""
    )

    assert completed.returncode != 0
    assert "Music.appへのアクセスがmacOSに拒否されました" in completed.stderr
    assert "(-1743)" in completed.stderr
