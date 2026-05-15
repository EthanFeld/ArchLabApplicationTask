from __future__ import annotations

import math
from typing import Any


def _saturating_brightness(pixel: int, brightness: int) -> int:
    return min(255, pixel + brightness)


def _rounded_average(running_sum: int, count: int) -> int:
    return (running_sum + (count // 2)) // count


def build_brightness_case(width: int, height: int, pixels: list[int], brightness: int) -> dict[str, Any]:
    """Build the canonical exact brightness test case for the baseline kernel.

    This is the simplest execution mode in the repository:

    - one GPU thread maps to one pixel
    - input pixels are stored linearly starting at data-memory address 0
    - the kernel adds a constant brightness offset with saturation at 255

    The returned dictionary is the common "case" format consumed by the cocotb
    harness. It contains both:

    - the raw data payload that should be loaded into simulated memory
    - the exact CPU-computed reference output used for correctness checking
    """
    expected_pixels = [_saturating_brightness(pixel, brightness) for pixel in pixels]
    return {
        "mode": "brightness",
        "kernel": "brightness.asm",
        "symbols": {"K": brightness},
        "data": pixels,
        "expected_pixels": expected_pixels,
        "metadata": {"brightness": brightness},
        "width": width,
        "height": height,
    }


def build_brightness_persistent_case(
    width: int,
    height: int,
    pixels: list[int],
    brightness: int,
    launch_threads: int,
    unroll_factor: int = 4,
) -> dict[str, Any]:
    """Build an exact persistent-thread brightness case.

    Persistent mode keeps the launch size fixed at hardware residency and lets
    each launched thread process multiple pixels using a grid-stride loop.
    This reduces launch/control overhead compared with one-thread-per-pixel.

    Memory layout produced here:

    - `data[0]`: iteration count per launched thread
    - `data[1]`: launch stride, usually total launched threads
    - `data[2..]`: padded pixel buffer

    Padding is intentional. The persistent kernel walks a rectangular work
    domain of `iterations * launch_threads * unroll_factor` pixels, so the host
    pads the tail with zeros and then checks only the original pixel count.
    """
    expected_pixels = [_saturating_brightness(pixel, brightness) for pixel in pixels]
    iterations = (len(pixels) + (launch_threads * unroll_factor) - 1) // (launch_threads * unroll_factor)
    padded_pixels = iterations * launch_threads * unroll_factor
    padded_data = pixels + ([0] * (padded_pixels - len(pixels)))

    return {
        "mode": "brightness-persistent",
        "kernel": "brightness_persistent.asm",
        "symbols": {"K": brightness},
        "data": [iterations, launch_threads] + padded_data,
        "expected_pixels": expected_pixels,
        "metadata": {
            "brightness": brightness,
            "launch_threads": launch_threads,
            "iterations_per_thread": iterations,
            "unroll_factor": unroll_factor,
            "pixels_per_thread": iterations * unroll_factor,
            "padding_pixels": padded_pixels - len(pixels),
        },
        "thread_count": launch_threads,
        "output_offset": 2,
        "width": width,
        "height": height,
    }


def build_brightness_cliques(
    pixels: list[int],
    threshold: int,
) -> list[dict[str, int]]:
    """Compress contiguous pixels into similarity cliques.

    A clique is a run of neighboring pixels whose observed value range
    (`max - min`) stays within `threshold`. For each clique we keep:

    - start index in the original pixel stream
    - run length
    - representative value, computed as rounded mean of the run
    - min and max values, mainly for statistics and debugging

    This is the core host-side approximation algorithm used by the
    clique-based extensions. The GPU later brightens only the representative
    values instead of every original pixel.
    """
    if threshold < 0:
        raise ValueError("threshold must be non-negative")
    if not pixels:
        return []

    cliques: list[dict[str, int]] = []
    start = 0
    count = 1
    min_value = pixels[0]
    max_value = pixels[0]
    running_sum = pixels[0]

    for index, pixel in enumerate(pixels[1:], start=1):
        next_min = min(min_value, pixel)
        next_max = max(max_value, pixel)
        if next_max - next_min <= threshold:
            count += 1
            min_value = next_min
            max_value = next_max
            running_sum += pixel
            continue

        representative = _rounded_average(running_sum, count)
        cliques.append(
            {
                "start": start,
                "length": count,
                "representative": representative,
                "min_value": min_value,
                "max_value": max_value,
            }
        )
        start = index
        count = 1
        min_value = pixel
        max_value = pixel
        running_sum = pixel

    representative = _rounded_average(running_sum, count)
    cliques.append(
        {
            "start": start,
            "length": count,
            "representative": representative,
            "min_value": min_value,
            "max_value": max_value,
        }
    )
    return cliques


def expand_cliques_to_pixels(cliques: list[dict[str, int]], brightness: int) -> list[int]:
    """Expand clique descriptors back into an approximate output pixel stream.

    Each clique contributes `length` copies of one brightened representative.
    This reconstructs the approximate image that should result from the
    clique-compression path after the GPU processes the representatives.
    """
    pixels: list[int] = []
    for clique in cliques:
        value = _saturating_brightness(int(clique["representative"]), brightness)
        pixels.extend([value] * int(clique["length"]))
    return pixels


def _build_brightness_clique_persistent_case_from_cliques(
    cliques: list[dict[str, int]],
    brightness: int,
    threshold: int,
    launch_threads: int,
    pixel_count: int,
) -> dict[str, Any]:
    """Build persistent-thread clique case from precomputed cliques.

    This is the shared packing logic behind the persistent clique extensions.
    The GPU sees a descriptor array rather than raw pixels.

    Memory layout:

    - `data[0]`: iteration count per launched thread
    - `data[1]`: launch stride
    - `data[2]`: actual clique count
    - `data[3..]`: `[run_length, representative]` pairs

    Descriptor pairs are padded out to a full persistent launch so the kernel
    can use a simple grid-stride loop without bounds checks for every step.
    """
    expected_pixels = expand_cliques_to_pixels(cliques, brightness=brightness)
    iterations = (len(cliques) + launch_threads - 1) // launch_threads
    padded_cliques = iterations * launch_threads

    data = [iterations, launch_threads, len(cliques)]
    for clique in cliques:
        data.extend([int(clique["length"]), int(clique["representative"])])
    data.extend([0, 0] * (padded_cliques - len(cliques)))

    avg_clique_size = (pixel_count / len(cliques)) if cliques else 0.0
    max_range = max((int(clique["max_value"]) - int(clique["min_value"]) for clique in cliques), default=0)
    return {
        "mode": "brightness-clique-approx",
        "kernel": "brightness_clique_approx_persistent.asm",
        "symbols": {"K": brightness},
        "data": data,
        "expected_pixels": expected_pixels,
        "metadata": {
            "brightness": brightness,
            "threshold": threshold,
            "clique_count": len(cliques),
            "avg_clique_size": avg_clique_size,
            "max_clique_range": max_range,
            "launch_threads": launch_threads,
            "iterations_per_thread": iterations,
            "padding_cliques": padded_cliques - len(cliques),
        },
        "thread_count": launch_threads,
        "result_count": len(cliques),
        "result_layout": "run_length_values",
        "descriptor_base": 3,
        "descriptor_stride": 2,
        "value_offset": 1,
        "width": pixel_count,
        "height": 1,
    }


def build_brightness_clique_case(
    width: int,
    height: int,
    pixels: list[int],
    brightness: int,
    threshold: int,
) -> dict[str, Any]:
    """Build the simple non-persistent clique approximation case.

    In this mode:

    - the host compresses contiguous similar pixels into cliques
    - one GPU thread handles one clique descriptor
    - the GPU brightens only the representative field in each descriptor
    - the host expands the brightened descriptors back into output pixels

    This reduces GPU work when many neighboring pixels are similar, but the
    result is approximate because each run is replaced by one representative.
    """
    cliques = build_brightness_cliques(pixels, threshold=threshold)
    expected_pixels = expand_cliques_to_pixels(cliques, brightness=brightness)
    data = [len(cliques)]
    for clique in cliques:
        data.extend([int(clique["length"]), int(clique["representative"])])

    avg_clique_size = (len(pixels) / len(cliques)) if cliques else 0.0
    max_range = max((int(clique["max_value"]) - int(clique["min_value"]) for clique in cliques), default=0)
    return {
        "mode": "brightness-clique-approx",
        "kernel": "brightness_clique_approx.asm",
        "symbols": {"K": brightness},
        "data": data,
        "expected_pixels": expected_pixels,
        "metadata": {
            "brightness": brightness,
            "threshold": threshold,
            "clique_count": len(cliques),
            "avg_clique_size": avg_clique_size,
            "max_clique_range": max_range,
        },
        "thread_count": len(cliques),
        "result_count": len(cliques),
        "result_layout": "run_length_values",
        "descriptor_base": 1,
        "descriptor_stride": 2,
        "value_offset": 1,
        "width": width,
        "height": height,
    }


def build_brightness_clique_persistent_case(
    pixels: list[int],
    brightness: int,
    threshold: int,
    launch_threads: int,
) -> dict[str, Any]:
    """Build the persistent-thread version of the clique approximation case.

    This combines two ideas:

    - host-side descriptor compression over similar pixel runs
    - fixed-residency GPU execution where each launched thread processes a
      grid-stride stream of clique descriptors

    It is useful when the descriptor count is still large enough that
    persistent execution can further amortize control overhead.
    """
    cliques = build_brightness_cliques(pixels, threshold=threshold)
    return _build_brightness_clique_persistent_case_from_cliques(
        cliques=cliques,
        brightness=brightness,
        threshold=threshold,
        launch_threads=launch_threads,
        pixel_count=len(pixels),
    )


def build_brightness_clique_batches(
    width: int,
    height: int,
    pixels: list[int],
    brightness: int,
    threshold: int,
    addr_bits: int,
    thread_count_bits: int,
    launch_threads: int,
) -> dict[str, Any]:
    """Split a large clique workload into multiple persistent batches.

    The persistent clique format must fit both:

    - data-memory capacity
    - maximum thread-count bookkeeping capacity

    For large images or low-compression cases, all clique descriptors may not
    fit in one launch. This helper computes the maximum safe clique count per
    batch, slices the descriptor stream accordingly, and produces one case per
    batch plus the full expected reconstructed output.
    """
    cliques = build_brightness_cliques(pixels, threshold=threshold)
    max_padded_cliques_by_memory = ((2**addr_bits - 3) // 2 // launch_threads) * launch_threads
    max_padded_cliques_by_threads = ((2**thread_count_bits - 1) // launch_threads) * launch_threads
    max_cliques_per_batch = min(max_padded_cliques_by_memory, max_padded_cliques_by_threads)
    if max_cliques_per_batch < launch_threads:
        raise ValueError("Configuration cannot fit any clique descriptors")

    batches = []
    total_expected_pixels: list[int] = []
    total_clique_count = len(cliques)

    for batch_index, start in enumerate(range(0, len(cliques), max_cliques_per_batch)):
        batch_cliques = cliques[start : start + max_cliques_per_batch]
        batch_pixels = sum(int(clique["length"]) for clique in batch_cliques)
        batch_expected = expand_cliques_to_pixels(batch_cliques, brightness=brightness)
        total_expected_pixels.extend(batch_expected)
        batches.append(
            {
                "index": batch_index,
                "clique_count": len(batch_cliques),
                "pixel_count": batch_pixels,
                "case": _build_brightness_clique_persistent_case_from_cliques(
                    cliques=batch_cliques,
                    brightness=brightness,
                    threshold=threshold,
                    launch_threads=launch_threads,
                    pixel_count=batch_pixels,
                ),
            }
        )

    avg_clique_size = (len(pixels) / total_clique_count) if total_clique_count else 0.0
    max_range = max((int(clique["max_value"]) - int(clique["min_value"]) for clique in cliques), default=0)
    return {
        "batches": batches,
        "expected_pixels": total_expected_pixels,
        "metadata": {
            "brightness": brightness,
            "threshold": threshold,
            "clique_count": total_clique_count,
            "batch_count": len(batches),
            "avg_clique_size": avg_clique_size,
            "max_clique_range": max_range,
            "max_cliques_per_batch": max_cliques_per_batch,
        },
        "width": width,
        "height": height,
    }


def plan_adaptive_brightness_tiles(
    width: int,
    height: int,
    addr_bits: int,
    launch_threads: int,
    unroll_factor: int = 4,
    header_words: int = 2,
) -> dict[str, Any]:
    """Plan how to tile a large image for persistent brightness execution.

    The baseline persistent kernel can only process a tile that fits within the
    configured data-memory size after padding to the persistent launch shape.
    This function computes a legal tiling plan.

    Strategy:

    - determine how many padded pixels fit after reserving header words
    - prefer full image width when possible
    - otherwise fall back to row-segment tiles
    - ensure every produced tile still fits after padding to
      `launch_threads * unroll_factor`

    The return value is a plan dictionary used by `run_brightness.py` to slice
    inputs, run each tile independently, and merge results back.
    """
    total_words = 2**addr_bits
    usable_words = total_words - header_words
    padded_chunk = launch_threads * unroll_factor
    max_padded_pixels = usable_words - (usable_words % padded_chunk)

    if max_padded_pixels <= 0:
        raise ValueError(
            "Configuration cannot fit one persistent tile: "
            f"addr_bits={addr_bits}, launch_threads={launch_threads}, unroll_factor={unroll_factor}"
        )

    if width <= max_padded_pixels:
        tile_width = width
        tile_height = max(1, min(height, max_padded_pixels // width))
    else:
        tile_width = max_padded_pixels
        tile_height = 1

    tiles = []
    tile_index = 0
    for top in range(0, height, tile_height):
        current_height = min(tile_height, height - top)
        for left in range(0, width, tile_width):
            current_width = min(tile_width, width - left)
            tile_pixels = current_width * current_height
            padded_pixels = ((tile_pixels + padded_chunk - 1) // padded_chunk) * padded_chunk
            if padded_pixels > max_padded_pixels:
                raise ValueError(
                    "Computed tile exceeds padded capacity: "
                    f"{current_width}x{current_height} -> {padded_pixels} > {max_padded_pixels}"
                )
            tiles.append(
                {
                    "index": tile_index,
                    "left": left,
                    "top": top,
                    "width": current_width,
                    "height": current_height,
                    "pixels": tile_pixels,
                    "padded_pixels": padded_pixels,
                }
            )
            tile_index += 1

    return {
        "tile_width": tile_width,
        "tile_height": tile_height,
        "tile_count": len(tiles),
        "max_padded_pixels": max_padded_pixels,
        "launch_threads": launch_threads,
        "unroll_factor": unroll_factor,
        "header_words": header_words,
        "tiles": tiles,
    }


def extract_image_tile(
    pixels: list[int],
    image_width: int,
    left: int,
    top: int,
    tile_width: int,
    tile_height: int,
) -> list[int]:
    """Copy a rectangular tile from a linear row-major image buffer."""
    tile_pixels: list[int] = []
    for row in range(top, top + tile_height):
        start = row * image_width + left
        tile_pixels.extend(pixels[start : start + tile_width])
    return tile_pixels


def merge_image_tile(
    output_pixels: list[int],
    image_width: int,
    left: int,
    top: int,
    tile_width: int,
    tile_height: int,
    tile_pixels: list[int],
) -> None:
    """Write a rectangular tile back into a linear row-major image buffer."""
    cursor = 0
    for row in range(top, top + tile_height):
        start = row * image_width + left
        end = start + tile_width
        output_pixels[start:end] = tile_pixels[cursor : cursor + tile_width]
        cursor += tile_width


def build_adaptive_gamma_lut(
    pixels: list[int],
    target_mean: float = 0.5,
    min_gamma: float = 0.35,
) -> tuple[list[int], float, float]:
    """Build a 256-entry adaptive gamma lookup table for one image.

    The host computes global mean luminance and derives a gamma value that
    brightens dark images toward `target_mean` while clamping gamma to the
    range `[min_gamma, 1.0]`.

    Returns:

    - LUT: 256-entry mapping from input intensity to output intensity
    - gamma: gamma actually chosen for this image
    - mean_luminance: normalized mean of the original image

    This keeps nonlinear math on the host and leaves the GPU kernel with only
    an indexed table lookup per pixel.
    """
    mean_luminance = sum(pixels) / (255.0 * len(pixels)) if pixels else 0.0
    safe_mean = max(mean_luminance, 1.0 / 255.0)

    if mean_luminance >= target_mean:
        gamma = 1.0
    else:
        gamma = math.log(target_mean) / math.log(safe_mean)
        gamma = min(1.0, max(min_gamma, gamma))

    lut = []
    for value in range(256):
        if value == 0:
            lut.append(0)
            continue
        normalized = value / 255.0
        lut.append(min(255, max(0, round(255.0 * (normalized**gamma)))))

    return lut, gamma, mean_luminance


def build_adaptive_gamma_lut_case(
    width: int,
    height: int,
    pixels: list[int],
    target_mean: float = 0.5,
    min_gamma: float = 0.35,
) -> dict[str, Any]:
    """Build the full LUT-based enhancement case for simulation.

    Memory layout:

    - image pixels start at address 0
    - the 256-entry LUT starts at address `width * height`

    The kernel reads one pixel, computes `lut_base + pixel_value`, loads the
    mapped output value, and stores it back in place. The returned case
    contains the exact host-generated reference output for correctness checks.
    """
    lut, gamma, mean_luminance = build_adaptive_gamma_lut(
        pixels,
        target_mean=target_mean,
        min_gamma=min_gamma,
    )
    expected_pixels = [lut[pixel] for pixel in pixels]
    return {
        "mode": "adaptive-gamma-lut",
        "kernel": "adaptive_gamma_lut.asm",
        "symbols": {"WIDTH": width, "HEIGHT": height},
        "data": pixels + lut,
        "expected_pixels": expected_pixels,
        "metadata": {
            "gamma": gamma,
            "target_mean": target_mean,
            "min_gamma": min_gamma,
            "mean_luminance": mean_luminance,
            "lut_base": width * height,
        },
        "width": width,
        "height": height,
    }
