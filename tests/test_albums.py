from pathlib import Path

from endless_vgm.albums import build_album_groups
from endless_vgm.models import Track


def make_track(
    track_id: str,
    album: str,
    playlist_index: int,
    *,
    disc_number: int | None = None,
    track_number: int | None = None,
) -> Track:
    return Track(
        id=track_id,
        playlist="GAME",
        playlist_index=playlist_index,
        name=track_id,
        artist="Composer",
        album_artist="Composer",
        album=album,
        location=Path(f"/music/{track_id}.m4a"),
        disc_number=disc_number,
        track_number=track_number,
    )


def test_groups_disc_variants_and_orders_discs_numerically() -> None:
    tracks = (
        make_track("disc2", "Final Fantasy IX [Disc 2]", 1, disc_number=2),
        make_track(
            "disc1a",
            "FINAL FANTASY IX Original Soundtrack [Disc 1]",
            2,
            disc_number=1,
        ),
        make_track(
            "disc1b",
            "FINAL FANTASY IX Original Soundtrack [Disc 1]",
            3,
            disc_number=1,
        ),
        make_track(
            "disc3",
            "FINAL FANTASY IX Original Soundtrack [Disc 3]",
            4,
            disc_number=3,
        ),
    )

    groups = build_album_groups(tracks)

    assert len(groups) == 1
    assert groups[0].name == "FINAL FANTASY IX Original Soundtrack"
    assert groups[0].disc_count == 3
    assert [track.id for track in groups[0].tracks] == [
        "disc1a",
        "disc1b",
        "disc2",
        "disc3",
    ]


def test_keeps_similar_nier_releases_separate() -> None:
    tracks = (
        make_track(
            "automata1",
            "NieR:Automata Original Soundtrack [Disc 1]",
            1,
            disc_number=1,
        ),
        make_track(
            "automata2",
            "NieR:Automata Original Soundtrack [Disc 2]",
            2,
            disc_number=2,
        ),
        make_track("orchestral", "NieR:Automata Orchestral Arrangement Album", 3),
        make_track("anime", "NieR:Automata Ver1.1a ORIGINAL SOUNDTRACK", 4),
        make_track("hacking", "NieR:Automata Original Soundtrack HACKING TRACKS", 5),
    )

    groups = build_album_groups(tracks)

    assert len(groups) == 4
    merged = next(group for group in groups if group.disc_count == 2)
    assert [track.id for track in merged.tracks] == ["automata1", "automata2"]
    assert {group.name for group in groups if group.disc_count == 1} == {
        "NieR:Automata Orchestral Arrangement Album",
        "NieR:Automata Ver1.1a ORIGINAL SOUNDTRACK",
        "NieR:Automata Original Soundtrack HACKING TRACKS",
    }


def test_groups_unnumbered_disc_when_track_metadata_identifies_it() -> None:
    tracks = (
        make_track(
            "culdcept1",
            "Culdcept DS Original Sound Track Deluxe",
            1,
            disc_number=1,
        ),
        make_track(
            "culdcept2",
            "Culdcept DS Original Sound Track Deluxe [Disc 2]",
            2,
            disc_number=2,
        ),
    )

    groups = build_album_groups(tracks)

    assert len(groups) == 1
    assert groups[0].disc_count == 2
    assert [track.id for track in groups[0].tracks] == ["culdcept1", "culdcept2"]


def test_leaves_ambiguous_unnumbered_release_out_of_numbered_group() -> None:
    tracks = (
        make_track("original", "デビルサマナー・ソウルハッカーズ", 1),
        make_track(
            "soundtrack1",
            "デビルサマナー ソウルハッカーズ オリジナル・サウンドトラック [Disc 1]",
            2,
            disc_number=1,
        ),
        make_track(
            "soundtrack2",
            "デビルサマナー ソウルハッカーズ オリジナル・サウンドトラック [Disc 2]",
            3,
            disc_number=2,
        ),
    )

    groups = build_album_groups(tracks)

    assert len(groups) == 2
    assert next(group for group in groups if group.disc_count == 1).tracks[0].id == "original"
    merged = next(group for group in groups if group.disc_count == 2)
    assert [track.id for track in merged.tracks] == [
        "soundtrack1",
        "soundtrack2",
    ]
