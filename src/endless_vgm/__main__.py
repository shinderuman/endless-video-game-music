from __future__ import annotations

import argparse
import logging
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

from .analysis import LoopAnalyzer
from .artwork import ArtworkExporter
from .library import MusicLibrary
from .server import PlayerApplication, PlayerServer


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
    parser.add_argument("-H", "--host", default="127.0.0.1", help="listen host")
    parser.add_argument("-p", "--port", type=int, default=8765, help="listen port")
    parser.add_argument("-o", "--open-browser", action="store_true", help="open browser")
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
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    package_dir = Path(__file__).resolve().parent
    cache_root = Path.home() / "Library" / "Caches" / "Endless Video Game Music"
    library = MusicLibrary(
        cache_root / "library.json",
        package_dir / "scripts" / "export_music_library.js",
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
        static_dir=package_dir / "static",
    )
    server = PlayerServer((args.host, args.port), app)
    url = f"http://{args.host}:{server.server_port}/"
    if args.open_browser:
        threading.Timer(0.2, lambda: webbrowser.open(url)).start()
    logging.getLogger(__name__).info("Endless VGM is running at %s", url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
