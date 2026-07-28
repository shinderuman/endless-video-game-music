from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from stage1_poc.runner import atomic_write_json, file_sha256

LOGGER = logging.getLogger(__name__)


def evaluation_key(seed: int, group_id: str, index: int, source_path: str) -> str:
    value = f"{seed}\0{group_id}\0{index}\0{source_path}".encode()
    return hashlib.sha256(value).hexdigest()


def playlist_tracks(cache: dict[str, Any], playlist_name: str) -> list[dict[str, Any]]:
    try:
        playlist = cache["playlists"][playlist_name]["playlist"]
    except (KeyError, TypeError) as error:
        raise ValueError(f"playlist not found in cache: {playlist_name}") from error
    tracks = playlist.get("tracks")
    if playlist.get("name") != playlist_name or not isinstance(tracks, list):
        raise ValueError(f"invalid cached playlist: {playlist_name}")
    return tracks


def select_group(
    cache: dict[str, Any],
    group: dict[str, Any],
    seed: int,
    used_paths: set[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    group_id = group["id"]
    albums = set(group.get("albums", []))
    candidates: list[tuple[str, int, dict[str, Any]]] = []
    seen_paths: set[str] = set()
    for index, track in enumerate(playlist_tracks(cache, group["sourcePlaylist"])):
        source_path = track.get("location", "")
        if not source_path or source_path in seen_paths or source_path in used_paths:
            continue
        if albums and track.get("album") not in albums:
            continue
        if not Path(source_path).is_file():
            continue
        seen_paths.add(source_path)
        candidates.append((evaluation_key(seed, group_id, index, source_path), index, track))
    sample_size = int(group["sampleSize"])
    if sample_size <= 0 or len(candidates) < sample_size:
        raise ValueError(
            f"group {group_id} has {len(candidates)} eligible tracks for sample size {sample_size}"
        )
    selected: list[dict[str, Any]] = []
    manifest_tracks: list[dict[str, Any]] = []
    for key, source_index, track in sorted(candidates)[:sample_size]:
        selected_track = {
            **track,
            "_evaluationGroup": group_id,
            "_defaultLabel": group.get("defaultLabel"),
        }
        selected.append(selected_track)
        used_paths.add(track["location"])
        manifest_tracks.append(
            {
                "selectionKey": key,
                "sourceOriginalIndex": source_index,
                "title": track.get("name", ""),
                "album": track.get("album", ""),
                "sourcePath": track["location"],
            }
        )
    return selected, {
        "id": group_id,
        "sourcePlaylist": group["sourcePlaylist"],
        "albums": sorted(albums),
        "defaultLabel": group.get("defaultLabel"),
        "eligibleCount": len(candidates),
        "selectedCount": len(selected),
        "tracks": manifest_tracks,
    }


def build_evaluation_cache(
    source_cache: dict[str, Any],
    source_cache_path: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    seed = int(config["seed"])
    output_playlist = config["outputPlaylist"]
    selected_tracks: list[dict[str, Any]] = []
    group_manifests: list[dict[str, Any]] = []
    used_paths: set[str] = set()
    for group in config["groups"]:
        selected, manifest = select_group(source_cache, group, seed, used_paths)
        selected_tracks.extend(selected)
        group_manifests.append(manifest)
    return {
        "version": 1,
        "evaluationSet": {
            "seed": seed,
            "sourceCache": str(source_cache_path),
            "sourceCacheSha256": file_sha256(source_cache_path),
            "groups": group_manifests,
            "trackCount": len(selected_tracks),
        },
        "playlists": {
            output_playlist: {
                "playlist": {
                    "name": output_playlist,
                    "tracks": selected_tracks,
                }
            }
        },
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a reproducible Stage 1 evaluation set.")
    parser.add_argument("-c", "--cache", type=Path, required=True)
    parser.add_argument("-f", "--config", type=Path, required=True)
    parser.add_argument("-o", "--output", type=Path, required=True)
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> None:
    source_cache = json.loads(args.cache.read_text(encoding="utf-8"))
    config = json.loads(args.config.read_text(encoding="utf-8"))
    result = build_evaluation_cache(source_cache, args.cache, config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(args.output, result)
    LOGGER.info(
        "wrote %d tracks to %s",
        result["evaluationSet"]["trackCount"],
        args.output,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        run(parse_args())
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        LOGGER.error("%s", error)
        raise SystemExit(1) from error
