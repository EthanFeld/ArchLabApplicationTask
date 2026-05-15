from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _parse_parameters(raw_parameters: list[str]) -> dict[str, int]:
    """Parse repeated `--parameter NAME=value` CLI arguments."""
    parsed: dict[str, int] = {}
    for item in raw_parameters:
        key, value = item.split("=", 1)
        parsed[key] = int(value, 0)
    return parsed


def _parse_env(raw_items: list[str]) -> dict[str, str]:
    """Parse repeated `--env NAME=value` CLI arguments."""
    parsed: dict[str, str] = {}
    for item in raw_items:
        key, value = item.split("=", 1)
        parsed[key] = value
    return parsed


def main() -> None:
    """CLI entry point for building the GPU and running one cocotb module.

    This wrapper exists so repository commands can stay short and consistent.
    It also mirrors selected compile-time parameters into environment variables
    that the Python testbench uses to size helper memory models correctly.
    """
    from tools.sim import build_gpu, run_cocotb

    parser = argparse.ArgumentParser(description="Build tiny-gpu and run one cocotb test module.")
    parser.add_argument("test_module")
    parser.add_argument("--build-name", default="default")
    parser.add_argument(
        "--parameter",
        action="append",
        default=[],
        help="Compile-time parameter override in the form NAME=value.",
    )
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        help="Extra environment variable for cocotb in the form NAME=value.",
    )
    args = parser.parse_args()

    parameters = _parse_parameters(args.parameter)
    extra_env = _parse_env(args.env)

    parameter_env = {
        "DATA_MEM_ADDR_BITS": "GPU_DATA_MEM_ADDR_BITS",
        "DATA_MEM_DATA_BITS": "GPU_DATA_MEM_DATA_BITS",
        "THREAD_COUNT_BITS": "GPU_THREAD_COUNT_BITS",
        "NUM_CORES": "GPU_NUM_CORES",
        "THREADS_PER_BLOCK": "GPU_THREADS_PER_BLOCK",
        "DATA_MEM_NUM_CHANNELS": "GPU_DATA_MEM_NUM_CHANNELS",
        "PROGRAM_MEM_NUM_CHANNELS": "GPU_PROGRAM_MEM_NUM_CHANNELS",
    }
    for parameter_name, env_name in parameter_env.items():
        if parameter_name in parameters:
            extra_env[env_name] = str(parameters[parameter_name])

    sim_binary = build_gpu(args.build_name, parameters)
    run_cocotb(sim_binary, args.test_module, extra_env=extra_env)


if __name__ == "__main__":
    main()
