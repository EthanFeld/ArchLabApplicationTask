from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

from tools.plots import PALETTE  # noqa: E402

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402


def _load_payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_time_plot(payload: dict, output_path: Path) -> None:
    reference = payload["reference_stats"]
    rows = [row for row in payload["thresholds"] if row["threshold"] <= 40]

    thresholds = [0] + [row["threshold"] for row in rows]
    wall_seconds = [reference["wall_seconds"]] + [row["wall_seconds"] for row in rows]
    cycles = [reference["cycles"]] + [row["cycles"] for row in rows]

    fig, ax = plt.subplots(figsize=(9.5, 5.2), constrained_layout=True)
    ax.plot(thresholds, wall_seconds, color=PALETTE["primary"], marker="o", linewidth=2.4, markersize=7)
    ax.fill_between(thresholds, wall_seconds, color=PALETTE["primary"], alpha=0.08)
    ax.set_title("Approximate Clique Sweep: Wall Time vs Threshold", fontsize=15, fontweight="semibold")
    ax.set_xlabel("Clique Threshold (T)")
    ax.set_ylabel("Wall Time (s)")
    ax.grid(alpha=0.9)

    for threshold, wall, cycle in zip(thresholds, wall_seconds, cycles):
        label = f"T={threshold}\n{wall:.1f}s\n{cycle:,} cyc"
        ax.annotate(
            label,
            (threshold, wall),
            textcoords="offset points",
            xytext=(0, 10 if threshold != 24 else -34),
            ha="center",
            color=PALETTE["text"],
            fontsize=8,
        )

    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def write_visual_grid(payload: dict, output_path: Path) -> None:
    base_dir = output_path.parent.parent
    rows = [row for row in payload["thresholds"] if row["threshold"] <= 40]
    entries = [
        {
            "threshold": 0,
            "image_path": base_dir / "green_parrot_512_exact.png",
            "title": "Exact (T=0)",
            "wall_seconds": payload["reference_stats"]["wall_seconds"],
            "psnr_db": None,
        }
    ]
    for row in rows:
        entries.append(
            {
                "threshold": row["threshold"],
                "image_path": output_path.parent / f"green_parrot_512_clique_t{row['threshold']}.png",
                "title": f"T={row['threshold']}",
                "wall_seconds": row["wall_seconds"],
                "psnr_db": row["psnr_db"],
            }
        )

    fig, axes = plt.subplots(2, 4, figsize=(14, 7.8), constrained_layout=True)
    fig.suptitle("Parrot Output Across Approximation Thresholds", fontsize=16, fontweight="semibold")

    for ax, entry in zip(axes.flat, entries):
        image = Image.open(entry["image_path"]).convert("L")
        ax.imshow(image, cmap="gray", vmin=0, vmax=255)
        if entry["psnr_db"] is None:
            subtitle = f"{entry['wall_seconds']:.1f}s"
        else:
            subtitle = f"{entry['wall_seconds']:.1f}s | {entry['psnr_db']:.1f} dB"
        ax.set_title(f"{entry['title']}\n{subtitle}", fontsize=10)
        ax.set_xticks([])
        ax.set_yticks([])

    for ax in axes.flat[len(entries) :]:
        ax.axis("off")

    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create threshold-sweep plots from a stored JSON summary.")
    parser.add_argument(
        "--input-json",
        type=Path,
        default=ROOT / "results" / "compare_approx" / "threshold_sweep" / "threshold_sweep.json",
    )
    parser.add_argument(
        "--time-plot",
        type=Path,
        default=ROOT / "results" / "compare_approx" / "threshold_sweep" / "threshold_sweep_time.png",
    )
    parser.add_argument(
        "--visual-grid",
        type=Path,
        default=ROOT / "results" / "compare_approx" / "threshold_sweep" / "threshold_sweep_visual.png",
    )
    args = parser.parse_args()

    payload = _load_payload(args.input_json)
    args.time_plot.parent.mkdir(parents=True, exist_ok=True)
    args.visual_grid.parent.mkdir(parents=True, exist_ok=True)

    write_time_plot(payload, args.time_plot)
    write_visual_grid(payload, args.visual_grid)


if __name__ == "__main__":
    main()
