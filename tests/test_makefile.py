from __future__ import annotations

import subprocess
from pathlib import Path


def make_stub(tmp_path: Path, *, exit_code: int, arguments_path: Path) -> Path:
    stub = tmp_path / "fake-uv"
    stub.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$@" > "{arguments_path}"\n'
        'echo "進捗 0%: スタブ開始"\n'
        'echo "進捗 100%: スタブ完了"\n'
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return stub


def run_library_target(
    tmp_path: Path,
    *,
    exit_code: int,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    log_path = tmp_path / "library-refresh.log"
    arguments_path = tmp_path / "arguments.txt"
    completed = subprocess.run(
        [
            "make",
            "library",
            f"UV={make_stub(tmp_path, exit_code=exit_code, arguments_path=arguments_path)}",
            f"LIBRARY_LOG={log_path}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed, log_path, arguments_path


def test_library_target_passes_log_path_and_displays_stub_progress(tmp_path) -> None:
    completed, log_path, arguments_path = run_library_target(tmp_path, exit_code=0)

    assert completed.returncode == 0
    assert "進捗 0%: スタブ開始" in completed.stdout
    assert "進捗 100%: スタブ完了" in completed.stdout
    arguments = arguments_path.read_text(encoding="utf-8").splitlines()
    assert arguments == [
        "run",
        "endless-vgm",
        "--refresh-library",
        "--library-log",
        str(log_path),
    ]


def test_library_target_preserves_failure_status_with_stub(tmp_path) -> None:
    completed, _, _ = run_library_target(tmp_path, exit_code=7)

    assert completed.returncode != 0
    assert "進捗 100%: スタブ完了" in completed.stdout


def test_backend_launcher_exposes_app_and_homebrew_binaries() -> None:
    launcher = Path("scripts/endless-vgm-backend").read_text(encoding="utf-8")

    assert '$app_root/.venv/bin:/opt/homebrew/bin:/usr/local/bin:$PATH' in launcher
    assert 'exec "$app_root/.venv/bin/python" -m endless_vgm' in launcher
