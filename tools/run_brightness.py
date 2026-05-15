from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.enhancement import (
    build_adaptive_gamma_lut_case,
    build_brightness_clique_batches,
    build_brightness_clique_case,
    extract_image_tile,
    build_brightness_case,
    build_brightness_persistent_case,
    merge_image_tile,
    plan_adaptive_brightness_tiles,
)
from tools.sim import ROOT, build_gpu, run_cocotb


def _build_name(
    mode: str,
    addr_bits: int,
    data_bits: int,
    thread_count_bits: int,
    num_cores: int,
    threads_per_block: int,
    data_mem_channels: int,
    program_mem_channels: int,
) -> str:
    """Build a deterministic simulator-build name from runtime configuration.

    Different architectural parameters produce different generated Verilog and
    different simulator binaries. Encoding the configuration into the build
    directory name makes those artifacts easy to distinguish and reuse.
    """
    return (
        f"{mode}_a{addr_bits}_d{data_bits}_t{thread_count_bits}"
        f"_c{num_cores}_b{threads_per_block}_dm{data_mem_channels}_pm{program_mem_channels}"
    )


def _run_single_case(
    *,
    input_stem: str,
    case: dict,
    case_tag: str,
    trace: bool,
    sim_binary: Path,
    build_name: str,
    addr_bits: int,
    data_bits: int,
    thread_count_bits: int,
    num_cores: int,
    threads_per_block: int,
    data_mem_channels: int,
    program_mem_channels: int,
) -> dict:
    """Run one prepared enhancement case through cocotb and return result JSON.

    A "case" is the common host-side description used throughout the repo. It
    includes:

    - kernel name
    - initial data-memory contents
    - expected output semantics
    - metadata such as output layout or symbols

    This helper writes that case to disk, points the generic cocotb testbench
    at it through environment variables, runs simulation, and then reads the
    machine-generated result file back into Python.
    """
    build_dir = ROOT / "build" / build_name
    build_dir.mkdir(parents=True, exist_ok=True)

    case_path = build_dir / f"{input_stem}_{case_tag}_case.json"
    result_path = build_dir / f"{input_stem}_{case_tag}_result.json"
    case_path.write_text(json.dumps(case, indent=2), encoding="utf-8")

    run_cocotb(
        sim_binary,
        test_module="test.test_brightness",
        extra_env={
            "ENHANCEMENT_CASE_PATH": str(case_path),
            "ENHANCEMENT_RESULT_PATH": str(result_path),
            "GPU_DATA_MEM_ADDR_BITS": str(addr_bits),
            "GPU_DATA_MEM_DATA_BITS": str(data_bits),
            "GPU_THREAD_COUNT_BITS": str(thread_count_bits),
            "GPU_NUM_CORES": str(num_cores),
            "GPU_THREADS_PER_BLOCK": str(threads_per_block),
            "GPU_DATA_MEM_NUM_CHANNELS": str(data_mem_channels),
            "GPU_PROGRAM_MEM_NUM_CHANNELS": str(program_mem_channels),
            "ENHANCEMENT_TRACE": "1" if trace else "0",
        },
    )
    return json.loads(result_path.read_text(encoding="utf-8"))


def run_case(
    input_image: Path,
    output_image: Path,
    stats_json: Path,
    mode: str,
    brightness: int,
    addr_bits: int,
    data_bits: int,
    thread_count_bits: int,
    num_cores: int,
    threads_per_block: int,
    data_mem_channels: int,
    program_mem_channels: int,
    target_mean: float = 0.5,
    min_gamma: float = 0.35,
    clique_threshold: int = 4,
    trace: bool = False,
    sim_binary: Path | None = None,
) -> dict:
    """Run one image through one enhancement mode end-to-end.

    High-level flow:

    1. Load the input image and convert it to grayscale.
    2. Build the host-side case description for the selected mode.
    3. Build or reuse a simulator binary for the requested GPU parameters.
    4. Run simulation once or many times depending on the mode.
    5. Reconstruct the final output pixel stream.
    6. Write output image plus JSON statistics.

    Exact modes (`brightness`, `brightness-persistent`, `brightness-adaptive-tiles`,
    `adaptive-gamma-lut`) compare directly against exact host-generated outputs.

    Approximate clique mode is still checked exactly against the host-side
    approximation model chosen by the current threshold and batching strategy.
    """
    image = Image.open(input_image).convert("L")
    width, height = image.size
    pixels = list(image.tobytes())

    launch_threads = num_cores * threads_per_block

    if mode == "brightness":
        case = build_brightness_case(width, height, pixels, brightness)
    elif mode == "brightness-persistent":
        case = build_brightness_persistent_case(
            width,
            height,
            pixels,
            brightness,
            launch_threads=launch_threads,
        )
    elif mode == "adaptive-gamma-lut":
        case = build_adaptive_gamma_lut_case(
            width,
            height,
            pixels,
            target_mean=target_mean,
            min_gamma=min_gamma,
        )
    elif mode == "brightness-clique-approx":
        case = None
    elif mode == "brightness-adaptive-tiles":
        case = None
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    build_name = _build_name(
        mode=mode,
        addr_bits=addr_bits,
        data_bits=data_bits,
        thread_count_bits=thread_count_bits,
        num_cores=num_cores,
        threads_per_block=threads_per_block,
        data_mem_channels=data_mem_channels,
        program_mem_channels=program_mem_channels,
    )

    if sim_binary is None:
        sim_binary = build_gpu(
            build_name=build_name,
            parameters={
                "DATA_MEM_ADDR_BITS": addr_bits,
                "DATA_MEM_DATA_BITS": data_bits,
                "THREAD_COUNT_BITS": thread_count_bits,
                "NUM_CORES": num_cores,
                "THREADS_PER_BLOCK": threads_per_block,
                "DATA_MEM_NUM_CHANNELS": data_mem_channels,
                "PROGRAM_MEM_NUM_CHANNELS": program_mem_channels,
            },
        )

    started = perf_counter()

    if mode == "brightness-clique-approx":
        batch_plan = build_brightness_clique_batches(
            width=width,
            height=height,
            pixels=pixels,
            brightness=brightness,
            threshold=clique_threshold,
            addr_bits=addr_bits,
            thread_count_bits=thread_count_bits,
            launch_threads=launch_threads,
        )
        output_pixels = []
        total_cycles = 0

        for batch in batch_plan["batches"]:
            batch_result = _run_single_case(
                input_stem=input_image.stem,
                case=batch["case"],
                case_tag=f"k{brightness}_clique_batch_{batch['index']}",
                trace=trace,
                sim_binary=sim_binary,
                build_name=build_name,
                addr_bits=addr_bits,
                data_bits=data_bits,
                thread_count_bits=thread_count_bits,
                num_cores=num_cores,
                threads_per_block=threads_per_block,
                data_mem_channels=data_mem_channels,
                program_mem_channels=program_mem_channels,
            )
            output_pixels.extend(batch_result["pixels"])
            total_cycles += int(batch_result["cycles"])

        result = {
            "width": width,
            "height": height,
            "mode": mode,
            "cycles": total_cycles,
            "pixels": output_pixels,
            "metadata": batch_plan["metadata"],
        }
    elif mode == "brightness-adaptive-tiles":
        plan = plan_adaptive_brightness_tiles(
            width=width,
            height=height,
            addr_bits=addr_bits,
            launch_threads=launch_threads,
        )
        output_pixels = [0] * (width * height)
        total_cycles = 0

        for tile in plan["tiles"]:
            tile_pixels = extract_image_tile(
                pixels=pixels,
                image_width=width,
                left=tile["left"],
                top=tile["top"],
                tile_width=tile["width"],
                tile_height=tile["height"],
            )
            tile_case = build_brightness_persistent_case(
                width=tile["width"],
                height=tile["height"],
                pixels=tile_pixels,
                brightness=brightness,
                launch_threads=launch_threads,
                unroll_factor=plan["unroll_factor"],
            )
            tile_result = _run_single_case(
                input_stem=input_image.stem,
                case=tile_case,
                case_tag=f"k{brightness}_tile_{tile['index']}",
                trace=trace,
                sim_binary=sim_binary,
                build_name=build_name,
                addr_bits=addr_bits,
                data_bits=data_bits,
                thread_count_bits=thread_count_bits,
                num_cores=num_cores,
                threads_per_block=threads_per_block,
                data_mem_channels=data_mem_channels,
                program_mem_channels=program_mem_channels,
            )
            merge_image_tile(
                output_pixels=output_pixels,
                image_width=width,
                left=tile["left"],
                top=tile["top"],
                tile_width=tile["width"],
                tile_height=tile["height"],
                tile_pixels=tile_result["pixels"],
            )
            total_cycles += int(tile_result["cycles"])

        result = {
            "width": width,
            "height": height,
            "mode": mode,
            "cycles": total_cycles,
            "pixels": output_pixels,
            "metadata": {
                "brightness": brightness,
                "launch_threads": launch_threads,
                "tile_count": plan["tile_count"],
                "tile_width": plan["tile_width"],
                "tile_height": plan["tile_height"],
                "max_padded_pixels": plan["max_padded_pixels"],
                "unroll_factor": plan["unroll_factor"],
            },
        }
    else:
        if mode == "brightness":
            suffix = f"k{brightness}"
        elif mode == "brightness-persistent":
            suffix = f"k{brightness}_persistent"
        elif mode == "brightness-clique-approx":
            suffix = f"k{brightness}_clique"
        else:
            suffix = "lut"
        result = _run_single_case(
            input_stem=input_image.stem,
            case=case,
            case_tag=suffix,
            trace=trace,
            sim_binary=sim_binary,
            build_name=build_name,
            addr_bits=addr_bits,
            data_bits=data_bits,
            thread_count_bits=thread_count_bits,
            num_cores=num_cores,
            threads_per_block=threads_per_block,
            data_mem_channels=data_mem_channels,
            program_mem_channels=program_mem_channels,
        )

    wall_seconds = perf_counter() - started

    output_image.parent.mkdir(parents=True, exist_ok=True)
    out = Image.new("L", (width, height))
    out.putdata(result["pixels"])
    out.save(output_image)

    stats = {
        "input_image": str(input_image),
        "output_image": str(output_image),
        "mode": mode,
        "width": width,
        "height": height,
        "pixels": width * height,
        "cycles": int(result["cycles"]),
        "wall_seconds": wall_seconds,
        "data_mem_addr_bits": addr_bits,
        "data_mem_data_bits": data_bits,
        "thread_count_bits": thread_count_bits,
        "num_cores": num_cores,
        "threads_per_block": threads_per_block,
        "data_mem_channels": data_mem_channels,
        "program_mem_channels": program_mem_channels,
    }
    stats.update(result.get("metadata", {}))
    if mode == "brightness":
        stats["brightness"] = brightness
    if mode == "brightness-clique-approx":
        stats["brightness"] = brightness
        stats["clique_threshold"] = clique_threshold

    stats_json.parent.mkdir(parents=True, exist_ok=True)
    stats_json.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    return stats


def main() -> None:
    """CLI entry point for running one enhancement mode on one image."""
    parser = argparse.ArgumentParser(description="Run one tiny-gpu image-enhancement kernel on one grayscale image.")
    parser.add_argument("input_image", type=Path)
    parser.add_argument("output_image", type=Path)
    parser.add_argument("--stats-json", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=(
            "brightness",
            "brightness-persistent",
            "brightness-clique-approx",
            "brightness-adaptive-tiles",
            "adaptive-gamma-lut",
        ),
        default="brightness",
    )
    parser.add_argument("--brightness", type=int, default=48)
    parser.add_argument("--clique-threshold", type=int, default=4)
    parser.add_argument("--addr-bits", type=int, default=16)
    parser.add_argument("--data-bits", type=int, default=16)
    parser.add_argument("--thread-count-bits", type=int, default=16)
    parser.add_argument("--num-cores", type=int, default=8)
    parser.add_argument("--threads-per-block", type=int, default=16)
    parser.add_argument("--data-mem-channels", type=int, default=16)
    parser.add_argument("--program-mem-channels", type=int, default=8)
    parser.add_argument("--target-mean", type=float, default=0.5)
    parser.add_argument("--min-gamma", type=float, default=0.35)
    parser.add_argument("--trace", action="store_true")
    args = parser.parse_args()

    stats = run_case(
        input_image=args.input_image,
        output_image=args.output_image,
        stats_json=args.stats_json,
        mode=args.mode,
        brightness=args.brightness,
        addr_bits=args.addr_bits,
        data_bits=args.data_bits,
        thread_count_bits=args.thread_count_bits,
        num_cores=args.num_cores,
        threads_per_block=args.threads_per_block,
        data_mem_channels=args.data_mem_channels,
        program_mem_channels=args.program_mem_channels,
        target_mean=args.target_mean,
        min_gamma=args.min_gamma,
        clique_threshold=args.clique_threshold,
        trace=args.trace,
    )
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
