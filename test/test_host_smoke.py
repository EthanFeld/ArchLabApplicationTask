from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.run_test import _parse_parameters

ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_parse_parameters_accepts_decimal_and_hex() -> None:
    parsed = _parse_parameters(["DATA_MEM_ADDR_BITS=16", "THREAD_COUNT_BITS=0x10"])

    assert parsed == {
        "DATA_MEM_ADDR_BITS": 16,
        "THREAD_COUNT_BITS": 16,
    }


def test_submission_satadd_command_passes() -> None:
    _run(
        [
            sys.executable,
            "tools/run_test.py",
            "test.test_brightness_satadd",
            "--build-name",
            "pytest_satadd",
            "--parameter",
            "DATA_MEM_ADDR_BITS=16",
            "--parameter",
            "DATA_MEM_DATA_BITS=16",
            "--parameter",
            "THREAD_COUNT_BITS=16",
        ]
    )


def test_submission_end_to_end_brightness_smoke(tmp_path: Path) -> None:
    output_image = tmp_path / "green_parrot_64_bright.png"
    stats_json = tmp_path / "green_parrot_64_stats.json"

    _run(
        [
            sys.executable,
            "tools/run_brightness.py",
            "inputs/green_parrot_64.png",
            str(output_image),
            "--stats-json",
            str(stats_json),
            "--brightness",
            "48",
        ]
    )

    stats = json.loads(stats_json.read_text(encoding="utf-8"))
    assert stats["mode"] == "brightness"
    assert stats["width"] == 64
    assert stats["height"] == 64
    assert stats["pixels"] == 4096
    assert stats["cycles"] > 0
    assert output_image.exists()
