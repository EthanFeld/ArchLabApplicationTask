from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter


PALETTE = {
    "primary": "#1f3a5f",
    "accent": "#d97706",
    "success": "#0f766e",
    "grid": "#d7dee8",
    "text": "#10233a",
    "muted": "#5b6b7f",
    "surface": "#f8fafc",
}


def _apply_style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": PALETTE["grid"],
            "axes.labelcolor": PALETTE["text"],
            "axes.titlecolor": PALETTE["text"],
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.titleweight": "semibold",
            "axes.labelsize": 11,
            "axes.titlesize": 14,
            "xtick.color": PALETTE["muted"],
            "ytick.color": PALETTE["muted"],
            "grid.color": PALETTE["grid"],
            "grid.linestyle": "--",
            "grid.linewidth": 0.8,
            "legend.frameon": False,
            "font.size": 10,
            "savefig.dpi": 180,
            "savefig.bbox": "tight",
        }
    )


def _int_compact(value: float, _: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return f"{value:.0f}"


def _seconds_formatter(value: float, _: int) -> str:
    return f"{value:.0f}s" if value >= 10 else f"{value:.1f}s"


def write_benchmark_plot(summary_rows: list[dict], output_path: Path, title: str) -> None:
    _apply_style()

    sizes = [row["image_size"] for row in summary_rows]
    cycles = [row["avg_cycles"] for row in summary_rows]
    wall = [row["avg_wall_seconds"] for row in summary_rows]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), constrained_layout=True)
    fig.suptitle(title, fontsize=16, fontweight="semibold", color=PALETTE["text"])

    axes[0].bar(sizes, cycles, color=PALETTE["primary"], width=0.58)
    axes[0].set_title("Average Cycles")
    axes[0].set_xlabel("Image Size")
    axes[0].set_ylabel("Cycles")
    axes[0].yaxis.set_major_formatter(FuncFormatter(_int_compact))
    axes[0].grid(axis="y", alpha=0.9)

    axes[1].bar(sizes, wall, color=PALETTE["accent"], width=0.58)
    axes[1].set_title("Average Wall Time")
    axes[1].set_xlabel("Image Size")
    axes[1].set_ylabel("Seconds")
    axes[1].yaxis.set_major_formatter(FuncFormatter(_seconds_formatter))
    axes[1].grid(axis="y", alpha=0.9)

    fig.savefig(output_path)
    plt.close(fig)


def write_scaling_plot(summary_rows: list[dict], output_path: Path, title: str) -> None:
    _apply_style()

    pixels = [row["pixels"] for row in summary_rows]
    image_sizes = [row["image_size"] for row in summary_rows]
    cycles = [row["avg_cycles"] for row in summary_rows]
    wall = [row["avg_wall_seconds"] for row in summary_rows]
    cpp = [row["cycles_per_pixel"] for row in summary_rows]

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), constrained_layout=True)
    fig.suptitle(title, fontsize=16, fontweight="semibold", color=PALETTE["text"])

    axes[0].plot(pixels, cycles, color=PALETTE["primary"], marker="o", linewidth=2.2, markersize=6)
    axes[0].fill_between(pixels, cycles, color=PALETTE["primary"], alpha=0.08)
    axes[0].set_title("Cycles vs. Pixels")
    axes[0].set_xlabel("Pixels")
    axes[0].set_ylabel("Cycles")
    axes[0].xaxis.set_major_formatter(FuncFormatter(_int_compact))
    axes[0].yaxis.set_major_formatter(FuncFormatter(_int_compact))
    axes[0].grid(alpha=0.9)

    axes[1].plot(pixels, wall, color=PALETTE["accent"], marker="o", linewidth=2.2, markersize=6)
    axes[1].fill_between(pixels, wall, color=PALETTE["accent"], alpha=0.08)
    axes[1].set_title("Wall Time vs. Pixels")
    axes[1].set_xlabel("Pixels")
    axes[1].set_ylabel("Seconds")
    axes[1].xaxis.set_major_formatter(FuncFormatter(_int_compact))
    axes[1].yaxis.set_major_formatter(FuncFormatter(_seconds_formatter))
    axes[1].grid(alpha=0.9)

    positions = list(range(len(image_sizes)))
    axes[2].plot(positions, cpp, color=PALETTE["success"], marker="o", linewidth=2.2, markersize=6)
    axes[2].fill_between(positions, cpp, color=PALETTE["success"], alpha=0.08)
    axes[2].set_title("Cycles per Pixel")
    axes[2].set_xlabel("Image Size")
    axes[2].set_ylabel("Cycles / Pixel")
    axes[2].set_xticks(positions, image_sizes)
    axes[2].grid(axis="y", alpha=0.9)

    fig.savefig(output_path)
    plt.close(fig)
