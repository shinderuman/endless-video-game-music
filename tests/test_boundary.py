from __future__ import annotations

import subprocess

import numpy as np
import pytest

from endless_vgm.boundary import (
    RefinedLoopBoundary,
    find_refined_loop_boundaries,
    find_refined_loop_boundaries_from_audio,
)


def test_refined_boundary_public_dict_uses_source_sample_rate() -> None:
    candidate = RefinedLoopBoundary(
        rank=-1,
        loop_start_sample=48_000,
        loop_end_sample=336_000,
        similarity=0.8,
        method="testMethod",
    )

    public = candidate.public_dict(48_000)

    assert public["rank"] == -1
    assert public["loopStartSeconds"] == 1
    assert public["loopEndSeconds"] == 7
    assert public["score"] == 0.8
    assert public["method"] == "testMethod"


@pytest.mark.parametrize("target_end_offset", [-0.4, 0.6])
def test_refinement_corrects_short_and_long_top_endpoints(
    target_end_offset: float,
) -> None:
    sample_rate = 8_000
    generator = np.random.default_rng(1234)
    loop = generator.normal(0, 0.2, (sample_rate * 6, 2))
    audio = np.tile(loop, (3, 1))
    loop_start = sample_rate
    target_end = round((7 + target_end_offset) * sample_rate)

    candidates = find_refined_loop_boundaries_from_audio(
        audio,
        sample_rate,
        loop_start,
        target_end,
    )

    assert [candidate.rank for candidate in candidates] == [0, -1, -2]
    assert candidates[0].loop_start_sample == loop_start
    assert candidates[0].loop_end_sample == pytest.approx(7 * sample_rate, abs=1)
    assert candidates[0].similarity > 0.99


def test_endpoint_pair_can_move_both_boundaries_without_changing_duration() -> None:
    sample_rate = 8_000
    generator = np.random.default_rng(2468)
    loop = generator.normal(0, 0.2, (sample_rate * 6, 2))
    loop[round(1.2 * sample_rate) : round(1.22 * sample_rate)] = 0
    audio = np.tile(loop, (3, 1))

    candidates = find_refined_loop_boundaries_from_audio(
        audio,
        sample_rate,
        sample_rate,
        7 * sample_rate,
    )

    loopmusic = candidates[1]
    auditioneer = candidates[2]
    assert loopmusic.loop_end_sample - loopmusic.loop_start_sample == 6 * sample_rate
    assert auditioneer.loop_end_sample - auditioneer.loop_start_sample == 6 * sample_rate
    assert loopmusic.loop_start_sample != sample_rate
    assert auditioneer.loop_start_sample != sample_rate


def test_refinement_rejects_invalid_or_silent_audio() -> None:
    silence = np.zeros((80_000, 2), dtype=np.float32)

    assert (
        find_refined_loop_boundaries_from_audio(
            silence,
            8_000,
            8_000,
            56_000,
        )
        == []
    )
    assert (
        find_refined_loop_boundaries_from_audio(
            silence,
            8_000,
            16_000,
            8_000,
        )
        == []
    )


def test_refinement_requires_channel_separated_audio() -> None:
    with pytest.raises(ValueError, match="channel-separated"):
        find_refined_loop_boundaries_from_audio(
            np.ones(80_000),
            8_000,
            8_000,
            56_000,
        )


def test_refinement_decodes_stereo_at_source_rate(tmp_path) -> None:
    generator = np.random.default_rng(5678)
    loop = generator.normal(0, 0.2, (60_000, 2)).astype(np.float32)
    audio = np.tile(loop, (3, 1))
    calls: list[list[str]] = []

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, audio.tobytes(), b"")

    candidates = find_refined_loop_boundaries(
        tmp_path / "music.m4a",
        10_000,
        70_000,
        10_000,
        command_runner=runner,
    )

    assert candidates
    assert calls[0][0] == "ffmpeg"
    assert calls[0][calls[0].index("-ac") + 1] == "2"
    assert calls[0][calls[0].index("-ar") + 1] == "10000"


def test_refinement_reports_ffmpeg_failure(tmp_path) -> None:
    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(command, 1, b"", b"decode failed")

    with pytest.raises(RuntimeError, match="decode failed"):
        find_refined_loop_boundaries(
            tmp_path / "broken.m4a",
            48_000,
            1_440_000,
            48_000,
            command_runner=runner,
        )
