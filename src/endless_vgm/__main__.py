from __future__ import annotations

import argparse
import contextlib
import logging
import os
import socket
from datetime import datetime
from pathlib import Path

from .server import PlayerApplication, PlayerUnixServer

LoopAnalyzer = None
ArtworkExporter = None
MusicLibrary = None
LibraryWatchdog = None


def _append_library_log(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output:
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        output.write(f"{timestamp} {message}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="endless-vgm",
        description="Music.appのローカル音源を自動解析してループ再生します。",
    )
    parser.add_argument(
        "-r",
        "--refresh-library",
        action="store_true",
        help="refresh Music.app library cache and exit",
    )
    parser.add_argument(
        "-L",
        "--library-log",
        type=Path,
        help="library refresh log path",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose logging")
    return parser


def main() -> None:
    global ArtworkExporter, LoopAnalyzer, MusicLibrary, LibraryWatchdog

    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    socket_path = os.environ.get("LOCAL_WEB_SOCKET")
    if not args.refresh_library and not socket_path:
        parser.error("LOCAL_WEB_SOCKET is required; launch through Local Web App Server")
    listener = None
    if socket_path:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(socket_path)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(socket_path)
        listener.listen()

    if LoopAnalyzer is None:
        from .analysis import LoopAnalyzer as loop_analyzer

        LoopAnalyzer = loop_analyzer
    if ArtworkExporter is None:
        from .artwork import ArtworkExporter as artwork_exporter

        ArtworkExporter = artwork_exporter
    if MusicLibrary is None:
        from .library import MusicLibrary as music_library

        MusicLibrary = music_library
    if LibraryWatchdog is None:
        from .watchdog import LibraryWatchdog as library_watchdog

        LibraryWatchdog = library_watchdog

    package_dir = Path(__file__).resolve().parent
    cache_root = Path.home() / "Library" / "Caches" / "Endless Video Game Music"
    library = MusicLibrary(
        cache_root / "library.json",
        package_dir / "scripts" / "export_music_library.js",
        manifest_script=package_dir / "scripts" / "export_playlist_manifest.js",
    )
    if args.refresh_library:
        log_path = args.library_log or cache_root / "library-refresh.log"
        logging.getLogger(__name__).info("Music.appライブラリの更新を開始します")
        try:
            library.refresh(show_progress=True, progress_log_path=log_path)
        except Exception as error:
            _append_library_log(log_path, f"失敗: {error}")
            raise
        logging.getLogger(__name__).info(
            "Music.appライブラリを更新しました（%dプレイリスト）",
            len(library.playlists()),
        )
        _append_library_log(
            log_path,
            f"完了: {len(library.playlists())}プレイリスト",
        )
        return
    library.load()
    app = PlayerApplication(
        library=library,
        analyzer=LoopAnalyzer(cache_root / "analysis"),
        artwork=ArtworkExporter(
            cache_root / "artwork",
            package_dir / "scripts" / "export_music_artwork.applescript",
        ),
    )
    assert socket_path is not None
    assert listener is not None
    server = PlayerUnixServer(socket_path, app, listener=listener)
    watchdog = LibraryWatchdog(library)
    watchdog.start()
    logging.getLogger(__name__).info("Endless VGM backend is ready")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        watchdog.stop()
        server.server_close()
        if socket_path:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(socket_path)


if __name__ == "__main__":
    main()
