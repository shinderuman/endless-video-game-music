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

    assert markup.elements["seek-bar"]["type"] == "range"
    assert {"current-time", "total-time"} <= markup.elements.keys()
