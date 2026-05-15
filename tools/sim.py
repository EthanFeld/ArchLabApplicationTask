from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _find_binary(env_var: str, which_name: str, *fallbacks: str) -> Path:
    explicit = os.environ.get(env_var)
    if explicit:
        path = Path(explicit)
        if path.exists():
            return path

    found = shutil.which(which_name)
    if found:
        return Path(found)

    for fallback in fallbacks:
        path = Path(fallback)
        if path.exists():
            return path

    raise FileNotFoundError(f"Unable to locate {which_name}. Set {env_var}.")


def _cocotb_config() -> Path:
    exe_suffix = ".exe" if os.name == "nt" else ""
    candidate = Path(sys.executable).with_name(f"cocotb-config{exe_suffix}")
    if candidate.exists():
        return candidate

    found = shutil.which("cocotb-config")
    if found:
        return Path(found)

    raise FileNotFoundError("Unable to locate cocotb-config in current Python environment.")


SV2V = _find_binary(
    "SV2V_BIN",
    "sv2v",
    str(ROOT / "tools" / "sv2v" / "sv2v-Windows" / "sv2v.exe"),
)
IVERILOG = _find_binary("IVERILOG_BIN", "iverilog", r"C:\iverilog\bin\iverilog.exe")
VVP = _find_binary("VVP_BIN", "vvp", r"C:\iverilog\bin\vvp.exe")


def _run_stdout(command: list[str]) -> str:
    return subprocess.check_output(command, text=True).strip()


def build_gpu(build_name: str, parameters: dict[str, int] | None = None) -> Path:
    parameters = parameters or {}
    build_dir = ROOT / "build" / build_name
    build_dir.mkdir(parents=True, exist_ok=True)

    raw_verilog = build_dir / "gpu.raw.v"
    output_verilog = build_dir / "gpu.v"
    sim_binary = build_dir / "sim.vvp"

    source_files = [str(path) for path in sorted((ROOT / "src").glob("*.sv"))]
    subprocess.run(
        [str(SV2V), "-I", str(ROOT / "src"), *source_files, "-w", str(raw_verilog)],
        check=True,
        cwd=ROOT,
    )

    output_verilog.write_text(
        "`timescale 1ns/1ns\n" + raw_verilog.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    compile_command = [str(IVERILOG), "-g2012", "-o", str(sim_binary), "-s", "gpu"]
    for key, value in parameters.items():
        compile_command.append(f"-Pgpu.{key}={value}")
    compile_command.append(str(output_verilog))

    subprocess.run(compile_command, check=True, cwd=ROOT)
    return sim_binary


def run_cocotb(
    sim_binary: Path,
    test_module: str,
    extra_env: dict[str, str] | None = None,
) -> None:
    cocotb_config = _cocotb_config()
    lib_dir = _run_stdout([str(cocotb_config), "--lib-dir"])
    lib_name = _run_stdout([str(cocotb_config), "--lib-name", "vpi", "icarus"])
    lib_python = _run_stdout([str(cocotb_config), "--libpython"])

    env = os.environ.copy()
    env["COCOTB_TEST_MODULES"] = test_module
    env["PYGPI_PYTHON_BIN"] = sys.executable
    env["LIBPYTHON_LOC"] = lib_python
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT), env["PYTHONPATH"]] if env.get("PYTHONPATH") else [str(ROOT)]
    )

    if extra_env:
        env.update({key: str(value) for key, value in extra_env.items()})

    subprocess.run(
        [str(VVP), "-M", lib_dir, "-m", lib_name, str(sim_binary)],
        check=True,
        cwd=ROOT,
        env=env,
    )
