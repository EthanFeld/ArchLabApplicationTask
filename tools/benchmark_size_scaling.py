from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.generate_inputs import SOURCE_FILENAMES, build_square_variant
from tools.plots import write_scaling_plot
from tools.run_brightness import run_case
from tools.sim import build_gpu


def _mode_tag(mode: str) -> str:
    """Convert CLI mode name into a filesystem-friendly tag."""
    return mode.replace("-", "_")


def _scaling_stem(mode: str) -> str:
    """Choose output filename stem for scaling artifacts."""
    return "brightness_scaling_extended" if mode == "brightness" else f"{_mode_tag(mode)}_scaling"


def _scaling_title(mode: str) -> str:
    """Choose human-readable plot title for a scaling run."""
    titles = {
        "brightness": "Brightness Scaling",
        "brightness-persistent": "Persistent Brightness Scaling",
        "brightness-clique-approx": "Approximate Clique Brightness Scaling",
        "brightness-adaptive-tiles": "Adaptive Tile Brightness Scaling",
        "adaptive-gamma-lut": "Adaptive Gamma LUT Scaling",
    }
    return titles[mode]


def main() -> None:
    """Benchmark one enhancement mode across many square image sizes.

    This script is the main source of the checked-in scaling evidence used in
    the README. It:

    - resizes source photos into square benchmark inputs
    - reuses one compiled simulator binary for all runs in the sweep
    - records per-run statistics
    - aggregates by image size across source images
    - writes JSON, Markdown, and plot artifacts
    """
    parser = argparse.ArgumentParser(description="Benchmark brightness kernel across many image sizes.")
    parser.add_argument("--sizes", nargs="+", type=int, default=[32, 64, 96, 128, 160, 192])
    parser.add_argument("--source-dir", type=Path, default=ROOT / "inputs")
    parser.add_argument("--source-stems", nargs="+", choices=sorted(SOURCE_FILENAMES.keys()), default=sorted(SOURCE_FILENAMES.keys()))
    parser.add_argument("--generated-dir", type=Path, default=ROOT / "results" / "scaling_inputs")
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
    parser.add_argument("--brightness", type=int, default=48)
    parser.add_argument("--clique-threshold", type=int, default=4)
    parser.add_argument("--addr-bits", type=int, default=16)
    parser.add_argument("--data-bits", type=int, default=16)
    parser.add_argument("--thread-count-bits", type=int, default=16)
    parser.add_argument("--num-cores", type=int, default=8)
    parser.add_argument("--threads-per-block", type=int, default=16)
    parser.add_argument("--data-mem-channels", type=int, default=16)
    parser.add_argument("--program-mem-channels", type=int, default=8)
    args = parser.parse_args()

    args.generated_dir.mkdir(parents=True, exist_ok=True)
    args.results_dir.mkdir(parents=True, exist_ok=True)

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

    runs = []
    grouped = defaultdict(list)

    for stem in args.source_stems:
        filename = SOURCE_FILENAMES[stem]
        source_path = args.source_dir / filename
        if not source_path.exists():
            raise FileNotFoundError(f"Missing source image: {source_path}")

        for size in args.sizes:
            generated_path = args.generated_dir / f"{stem}_{size}.png"
            build_square_variant(source_path, size).save(generated_path)

            stats = run_case(
                input_image=generated_path,
                output_image=args.results_dir / (
                    f"{generated_path.stem}_bright.png"
                    if args.mode == "brightness"
                    else f"{generated_path.stem}_{_mode_tag(args.mode)}_bright.png"
                ),
                stats_json=args.results_dir / (
                    f"{generated_path.stem}_stats.json"
                    if args.mode == "brightness"
                    else f"{generated_path.stem}_{_mode_tag(args.mode)}_stats.json"
                ),
                mode=args.mode,
                brightness=args.brightness,
                addr_bits=args.addr_bits,
                data_bits=args.data_bits,
                thread_count_bits=args.thread_count_bits,
                num_cores=args.num_cores,
                threads_per_block=args.threads_per_block,
                data_mem_channels=args.data_mem_channels,
                program_mem_channels=args.program_mem_channels,
                clique_threshold=args.clique_threshold,
                sim_binary=sim_binary,
            )
            runs.append(stats)
            grouped[(stats["width"], stats["height"])].append(stats)

    summary_rows = []
    for (width, height), items in sorted(grouped.items()):
        cycle_values = [item["cycles"] for item in items]
        wall_values = [item["wall_seconds"] for item in items]
        pixel_count = width * height
        summary_rows.append(
            {
                "image_size": f"{width}x{height}",
                "pixels": pixel_count,
                "avg_cycles": sum(cycle_values) / len(cycle_values),
                "avg_wall_seconds": sum(wall_values) / len(wall_values),
                "cycles_per_pixel": (sum(cycle_values) / len(cycle_values)) / pixel_count,
            }
        )

    payload = {
        "sizes": args.sizes,
        "source_stems": args.source_stems,
        "runs": runs,
        "summary": summary_rows,
    }
    scaling_stem = _scaling_stem(args.mode)
    (args.results_dir / f"{scaling_stem}.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )

    markdown_lines = [
        "| Image Size | Pixels | Avg Cycles | Avg Wall Time (s) | Cycles / Pixel |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in summary_rows:
        markdown_lines.append(
            f"| {row['image_size']} | {row['pixels']} | {row['avg_cycles']:.0f} | {row['avg_wall_seconds']:.3f} | {row['cycles_per_pixel']:.4f} |"
        )

    (args.results_dir / f"{scaling_stem}.md").write_text(
        "\n".join(markdown_lines) + "\n",
        encoding="utf-8",
    )

    write_scaling_plot(
        summary_rows=summary_rows,
        output_path=args.results_dir / f"{scaling_stem}.png",
        title=_scaling_title(args.mode),
    )

    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
