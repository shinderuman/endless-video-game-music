import sys
from pathlib import Path

from endless_vgm import __main__ as main_module
from endless_vgm.__main__ import build_parser


def test_short_command_line_options() -> None:
    args = build_parser().parse_args(
        [
            "-H",
            "0.0.0.0",
            "-p",
            "9000",
            "-o",
            "-r",
            "-L",
            "/tmp/library.log",
            "-v",
        ]
    )

    assert args.host == "0.0.0.0"
    assert args.port == 9000
    assert args.open_browser is True
    assert args.refresh_library is True
    assert args.library_log == Path("/tmp/library.log")
    assert args.verbose is True


def test_refresh_library_mode_updates_cache_and_exits(monkeypatch, tmp_path) -> None:
    calls: list[tuple[bool, Path | None]] = []

    class FakeLibrary:
        def __init__(self, *_: object) -> None:
            pass

        def refresh(
            self,
            *,
            show_progress: bool = False,
            progress_log_path: Path | None = None,
        ) -> None:
            calls.append((show_progress, progress_log_path))

        def playlists(self) -> tuple[object, ...]:
            return (object(), object())

    monkeypatch.setattr(main_module, "MusicLibrary", FakeLibrary)
    log_path = tmp_path / "library.log"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "endless-vgm",
            "--refresh-library",
            "--library-log",
            str(log_path),
        ],
    )

    main_module.main()

    assert calls == [(True, log_path)]
    assert "完了: 2プレイリスト" in log_path.read_text(encoding="utf-8")
