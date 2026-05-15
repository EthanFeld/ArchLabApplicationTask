from __future__ import annotations

import importlib.util
from pathlib import Path


_COCOTB_PRESENT = importlib.util.find_spec("cocotb") is not None
_HDL_TEST_ROOT = Path(__file__).resolve().parent / "test"
_HOST_SAFE_TESTS = {"test_host_smoke.py"}


def pytest_ignore_collect(collection_path: Path, config: object) -> bool:
    if _COCOTB_PRESENT:
        return False

    path = Path(str(collection_path))
    return (
        path.is_file()
        and path.suffix == ".py"
        and path.parent == _HDL_TEST_ROOT
        and path.name.startswith("test_")
        and path.name not in _HOST_SAFE_TESTS
    )


def pytest_report_header(config: object) -> str | None:
    if _COCOTB_PRESENT:
        return None

    return (
        "cocotb not installed in active Python; HDL tests skipped. "
        "Use `.venv\\Scripts\\python tools\\run_test.py <test_module>` per README."
    )
