from __future__ import annotations

import json
import subprocess

import pytest

from endless_vgm.analysis import LoopAnalyzer, parse_candidates
from endless_vgm.boundary import RefinedLoopBoundary
from endless_vgm.models import Track


def make_track(path) -> Track:
    return Track(
        id="a" * 24,
        playlist="GAME",
        playlist_index=1,
        name="Loop",
        artist="Composer",
        album_artist="Composer",
        album="Album",
        location=path,
    )


def make_analyzer(cache_dir, runner=subprocess.run) -> LoopAnalyzer:
    return LoopAnalyzer(
        cache_dir,
        command_runner=runner,
        boundary_finder=lambda _, loop_start, loop_end, __: [
            RefinedLoopBoundary(
                rank=0,
                loop_start_sample=loop_start,
                loop_end_sample=loop_end,
                similarity=0.8,
                method="pmlDurationLocalWaveform",
            )
        ],
    )


def test_parse_candidates_and_no_candidate() -> None:
    candidates = parse_candidates("48000 144000 0.1 0.2 0.95\n", 48000)

    assert len(candidates) == 1
    assert candidates[0].loop_start_seconds == 1
    assert candidates[0].loop_end_seconds == 3
    assert parse_candidates("No loop points found for track\n", 48000) == []


def test_parse_candidates_rejects_unknown_output() -> None:
    with pytest.raises(ValueError, match="Unexpected"):
        parse_candidates("not valid", 48000)


def test_analyze_sorts_candidates_and_uses_cache(tmp_path) -> None:
    audio = tmp_path / "music.m4a"
    audio.write_bytes(b"audio")
    calls: list[list[str]] = []

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[0] == "ffprobe":
            output = '{"streams":[{"sample_rate":"48000"}]}'
            return subprocess.CompletedProcess(command, 0, output, "")
        return subprocess.CompletedProcess(
            command,
            0,
            "0 48000 0.2 0.3 0.25\n48000 144000 0.1 0.1 0.99\n",
            "",
        )

    analyzer = make_analyzer(tmp_path / "analysis", runner)

    first = analyzer.analyze(make_track(audio))
    second = analyzer.analyze(make_track(audio))

    assert first == second
    assert first["candidateCount"] == 2
    assert first["candidates"][0]["score"] == 0.99
    assert first["candidates"][0]["rank"] == 1
    assert first["refinedCandidates"][0]["loopStartSeconds"] == 1.0
    assert first["refinedCandidates"][0]["loopEndSeconds"] == 3.0
    assert first["refinedCandidates"][0]["method"] == "pmlDurationLocalWaveform"
    assert len(calls) == 2


def test_analyze_rejects_unavailable_track(tmp_path) -> None:
    analyzer = make_analyzer(tmp_path / "analysis")

    with pytest.raises(FileNotFoundError):
        analyzer.analyze(make_track(tmp_path / "missing.m4a"))


def test_analyze_limits_candidates_to_top_twenty(tmp_path) -> None:
    audio = tmp_path / "music.m4a"
    audio.write_bytes(b"audio")

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if command[0] == "ffprobe":
            output = '{"streams":[{"sample_rate":"48000"}]}'
            return subprocess.CompletedProcess(command, 0, output, "")
        output = "\n".join(f"{index} {index + 48000} 0.1 0.1 {index / 100}" for index in range(25))
        return subprocess.CompletedProcess(command, 0, output, "")

    result = make_analyzer(tmp_path / "analysis", runner).analyze(make_track(audio))

    assert result["candidateCount"] == 20
    assert len(result["candidates"]) == 20
    assert result["candidates"][0]["score"] == 0.24
    assert result["candidates"][-1]["score"] == 0.05
    assert result["refinedCandidates"][0]["loopStartSeconds"] == 24 / 48_000
    assert result["refinedCandidates"][0]["loopEndSeconds"] == (24 + 48_000) / 48_000
    assert result["refinedCandidates"][0]["score"] == 0.8


def test_analyze_invalidates_older_cache_version(tmp_path) -> None:
    audio = tmp_path / "music.m4a"
    audio.write_bytes(b"audio")
    cache_dir = tmp_path / "analysis"
    cache_dir.mkdir()
    stat = audio.stat()
    (cache_dir / f"{'a' * 24}.json").write_text(
        json.dumps(
            {
                "source": {"size": stat.st_size, "mtimeNs": stat.st_mtime_ns},
                "candidateCount": 0,
                "candidates": [],
            }
        ),
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[0] == "ffprobe":
            output = '{"streams":[{"sample_rate":"48000"}]}'
            return subprocess.CompletedProcess(command, 0, output, "")
        return subprocess.CompletedProcess(command, 0, "0 48000 0.1 0.1 0.8\n", "")

    result = make_analyzer(cache_dir, runner).analyze(make_track(audio))

    assert result["refinedCandidates"][0]["loopStartSeconds"] == 0
    assert len(calls) == 2


def test_force_analysis_ignores_current_cache(tmp_path) -> None:
    audio = tmp_path / "music.m4a"
    audio.write_bytes(b"audio")
    calls: list[list[str]] = []

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[0] == "ffprobe":
            output = '{"streams":[{"sample_rate":"48000"}]}'
            return subprocess.CompletedProcess(command, 0, output, "")
        return subprocess.CompletedProcess(command, 0, "0 48000 0.1 0.1 0.8\n", "")

    analyzer = make_analyzer(tmp_path / "analysis", runner)
    track = make_track(audio)

    analyzer.analyze(track)
    analyzer.analyze(track, force=True)

    assert len(calls) == 4
