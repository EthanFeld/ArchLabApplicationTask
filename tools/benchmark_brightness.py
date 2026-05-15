from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.run_brightness import run_case
from tools.sim import ROOT, build_gpu
from tools.plots import write_benchmark_plot


def _mode_tag(mode: str) -> str:
    return mode.replace("-", "_")


def _benchmark_stem(mode: str) -> str:
    return "brightness_benchmark" if mode == "brightness" else f"{_mode_tag(mode)}_benchmark"


def _benchmark_title(mode: str) -> str:
    titles = {
        "brightness": "Brightness Benchmark",
        "brightness-persistent": "Persistent Brightness Benchmark",
        "brightness-clique-approx": "Approximate Clique Brightness Benchmark",
        "brightness-adaptive-tiles": "Adaptive Tile Brightness Benchmark",
        "adaptive-gamma-lut": "Adaptive Gamma LUT Benchmark",
    }
    return titles[mode]


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark one tiny-gpu image-enhancement mode on multiple input images.")
    parser.add_argument("--inputs", nargs="+", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results")
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
    parser.add_argument("--clique-threshold", type=int, default=4)
    parser.add_argument("--brightness", type=int, default=48)
    parser.add_argument("--addr-bits", type=int, default=16)
    parser.add_argument("--data-bits", type=int, default=16)
    parser.add_argument("--thread-count-bits", type=int, default=16)
    parser.add_argument("--num-cores", type=int, default=8)
    parser.add_argument("--threads-per-block", type=int, default=16)
    parser.add_argument("--data-mem-channels", type=int, default=16)
    parser.add_argument("--program-mem-channels", type=int, default=8)
    parser.add_argument("--target-mean", type=float, default=0.5)
    parser.add_argument("--min-gamma", type=float, default=0.35)
    args = parser.parse_args()

    results_dir = args.results_dir
    results_dir.mkdir(parents=True, exist_ok=True)

    runs = []
    grouped = defaultdict(list)
    sim_binary = build_gpu(
        build_name=(
            f"{args.mode}_a{args.addr_bits}_d{args.data_bits}_t{args.thread_count_bits}"
            f"_c{args.num_cores}_b{args.threads_per_block}_dm{args.data_mem_channels}_pm{args.program_mem_channels}"
        ),
        parameters={
            "DATA_MEM_ADDR_BITS": args.addr_bits,
            "DATA_MEM_DATA_BITS": args.data_bits,
            "THREAD_COUNT_BITS": args.thread_count_bits,
            "NUM_CORES": args.num_cores,
            "THREADS_PER_BLOCK": args.threads_per_block,
            "DATA_MEM_NUM_CHANNELS": args.data_mem_channels,
            "PROGRAM_MEM_NUM_CHANNELS": args.program_mem_channels,
        },
    )

    for input_path in args.inputs:
        suffix = "" if args.mode == "brightness" else f"_{_mode_tag(args.mode)}"
        output_image = results_dir / f"{input_path.stem}{suffix}_bright.png"
        stats_json = results_dir / f"{input_path.stem}{suffix}_stats.json"
        stats = run_case(
            input_image=input_path,
            output_image=output_image,
            stats_json=stats_json,
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
            sim_binary=sim_binary,
        )
        runs.append(stats)
        grouped[(stats["width"], stats["height"])].append(stats)

    summary_rows = []
    for (width, height), items in sorted(grouped.items()):
        cycle_values = [item["cycles"] for item in items]
        wall_values = [item["wall_seconds"] for item in items]
        summary_rows.append(
            {
                "image_size": f"{width}x{height}",
                "pixels": width * height,
                "avg_cycles": sum(cycle_values) / len(cycle_values),
                "avg_wall_seconds": sum(wall_values) / len(wall_values),
            }
        )

    payload = {"runs": runs, "summary": summary_rows}
    benchmark_stem = _benchmark_stem(args.mode)
    (results_dir / f"{benchmark_stem}.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )

    markdown_lines = [
        "| Image Size | Number of Pixels | Avg tiny-gpu Cycles | Avg Wall Time (s) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in summary_rows:
        markdown_lines.append(
            f"| {row['image_size']} | {row['pixels']} | {row['avg_cycles']:.0f} | {row['avg_wall_seconds']:.3f} |"
        )

    (results_dir / f"{benchmark_stem}.md").write_text(
        "\n".join(markdown_lines) + "\n",
        encoding="utf-8",
    )

    write_benchmark_plot(
        summary_rows=summary_rows,
        output_path=results_dir / f"{benchmark_stem}.png",
        title=_benchmark_title(args.mode),
    )

    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
