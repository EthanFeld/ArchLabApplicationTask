# tiny-gpu Image Brightness Adjustment

This repository contains my solution for the ARCH Lab `tiny-gpu` image-processing task:

```text
output(x, y) = min(255, input(x, y) + k)
```

Baseline design:

- grayscale input image stored as a 1D pixel array
- one tiny-gpu thread per pixel
- each thread loads one pixel, applies saturating brightness add, writes one result


## Repository Contents

Required assignment artifacts:

- `src/`: SystemVerilog RTL
- `kernels/brightness.asm`: baseline brightness kernel
- `test/`: cocotb testbench plus host-side smoke tests
- `inputs/`: sample input images
- `README.md`

Main submission files:

- `tools/run_brightness.py`: end-to-end runner for one image
- `tools/run_test.py`: cocotb/iverilog wrapper
- `results/brightness_scaling_extended.json`
- `results/brightness_scaling_extended.png`

Optional extension material remains in-tree, but baseline path above is primary submission.

## What I Changed

Inherited from `tiny-gpu`:

- overall RTL decomposition in `src/`
- simple SIMT execution model
- cocotb + Icarus simulation flow

Implemented or adapted for this task:

- grayscale brightness enhancement kernel
- `SATADD` instruction support used for clamp-to-255 behavior
- Python harness for image loading, grayscale conversion, exact CPU reference generation, and output checking
- benchmark scripts and checked-in scaling artifacts

## Quick Start

Create environment:

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

Required tools in `PATH`:

- `iverilog`
- `vvp`
- `sv2v`

Windows fallbacks and env overrides are supported:

- `C:\iverilog\bin\iverilog.exe`
- `C:\iverilog\bin\vvp.exe`
- `tools\sv2v\sv2v-Windows\sv2v.exe`
- `IVERILOG_BIN`
- `VVP_BIN`
- `SV2V_BIN`

## Submission Check

Recommended single command:

```powershell
.venv\Scripts\python -m pytest -q
```

This now exercises both:

- fast host-side unit tests
- submission-level smoke tests for the canonical HDL path

Equivalent Make target:

```powershell
make submit-check
```

##Baseline Commands

Run the baseline HDL smoke test directly:

```powershell
.venv\Scripts\python tools\run_test.py test.test_brightness_satadd --build-name satadd_test --parameter DATA_MEM_ADDR_BITS=16 --parameter DATA_MEM_DATA_BITS=16 --parameter THREAD_COUNT_BITS=16
```

Run one image end-to-end:

```powershell
.venv\Scripts\python tools\run_brightness.py `
  inputs\green_parrot_64.png `
  results\green_parrot_64_bright.png `
  --stats-json results\green_parrot_64_stats.json `
  --brightness 48
```

This flow:

- assembles `kernels/brightness.asm`
- initializes GPU memories
- runs cocotb + Icarus simulation
- checks every output pixel against an exact CPU reference
- writes output image and JSON stats

## Performance Evaluation

Checked-in baseline scaling artifacts:

- [`results/brightness_scaling_extended.json`](/c:/Users/ethan/github/bee/ArchLabApplicationTask/results/brightness_scaling_extended.json)
- [`results/brightness_scaling_extended.png`](/c:/Users/ethan/github/bee/ArchLabApplicationTask/results/brightness_scaling_extended.png)

Representative behavior from those runs:

- total cycles scale roughly linearly with pixel count
- cycles per pixel flatten as image size grows, which matches fixed control overhead amortization
- simulator wall time grows faster and is dominated partly by Python/cocotb/Icarus overhead

Regenerate the checked-in scaling summary with:

```powershell
.venv\Scripts\python tools\benchmark_size_scaling.py --sizes 32 64 96 128 160 192 --results-dir results --generated-dir results\scaling_inputs --brightness 48
```

## Design Notes

Pixel mapping:

- global thread id = `blockIdx * blockDim + threadIdx`
- pixel array is linear in memory
- each active thread owns one pixel address

Baseline kernel:

- load pixel
- `SATADD` with constant brightness factor
- store result
- return

This keeps address generation simple and makes correctness easy to explain during review.

## Limits

Current simplifications:

- no branch divergence handling
- no shared memory
- no warp scheduling
- no deep pipelining
- no burst-style memory coalescing
- one kernel launch at a time

With the current baseline `16-bit` address and thread-count configuration, the largest square image that fits in one clean baseline launch is `255x255`.

## Extensions

These are not required for the baseline:

- `brightness-persistent`
- `brightness-clique-approx`
- `brightness-adaptive-tiles`
- `adaptive-gamma-lut`

They are kept for comparison and follow-on experimentation, but they are not necessary to understand or grade the core submission.

### `brightness-persistent`

Files:

- `kernels/brightness_persistent.asm`
- `tools/enhancement.py`

Idea:

- baseline launch maps one thread to one pixel
- persistent mode instead launches a fixed resident thread set
- each launched thread walks a grid-stride stream of pixels
- current kernel uses `4x` loop unrolling to process four pixels per loop trip

Data layout:

- `data[0]`: iteration count per launched thread
- `data[1]`: launch stride
- `data[2..]`: padded pixel buffer

Why it helps:

- reduces dispatch and loop-control overhead per useful pixel
- better amortizes fixed costs when image is larger than hardware residency
- keeps computation exact, unlike approximation-based extensions

Tradeoffs:

- more complex host-side packing than baseline
- padded tail pixels may be processed but are excluded from checked output
- still limited by single-kernel memory capacity unless paired with tiling

### `brightness-clique-approx`

Files:

- `kernels/brightness_clique_approx.asm`
- `kernels/brightness_clique_approx_persistent.asm`
- `tools/enhancement.py`

Idea:

- host groups contiguous pixels into similarity "cliques"
- clique means run of neighboring pixels whose min/max range stays within a threshold
- each clique stores `run_length` plus one representative value
- GPU brightens representatives only
- host expands brightened representatives back to full pixel stream

Data layout:

- simple mode:
  `data[0] = clique_count`, then `[run_length, representative]` pairs
- persistent mode:
  `data[0] = iterations`, `data[1] = launch_stride`, `data[2] = actual_clique_count`, then padded descriptor pairs

Why it helps:

- if many adjacent pixels are already similar, GPU work scales with clique count instead of raw pixel count
- can reduce arithmetic and memory traffic for smooth regions
- persistent version combines descriptor compression with fixed-residency execution

Tradeoffs:

- this mode is approximate by construction
- output quality depends on threshold and image texture
- sharp edges and high-frequency detail produce more cliques, reducing compression benefit
- requires host preprocessing and post-expansion

### `brightness-adaptive-tiles`

Files:

- `tools/enhancement.py`
- `tools/run_brightness.py`

Idea:

- baseline cleanly fits only up to current single-launch capacity
- adaptive tiling breaks large image into tiles that each fit persistent-kernel constraints
- host extracts one tile, runs persistent brightness on that tile, then merges result back

Planning logic:

- compute maximum padded pixels allowed by current address width
- choose tile geometry that fits resident-thread chunk size
- fall back to row segments if image width alone exceeds tile capacity

Why it helps:

- extends exact brightness flow to images larger than single baseline launch
- preserves correctness because each tile is still checked against exact host reference
- can improve throughput by combining tiling with persistent-thread execution

Tradeoffs:

- more host orchestration
- repeated launch overhead across tiles
- boundary handling is simple because operation is pointwise, but more complex filters would need halo logic

### `adaptive-gamma-lut`

Files:

- `kernels/adaptive_gamma_lut.asm`
- `tools/enhancement.py`

Idea:

- instead of constant brightness offset, host computes global image mean luminance
- from that mean it derives a gamma value bounded by `min_gamma` and `1.0`
- host builds a 256-entry lookup table
- GPU applies enhancement by replacing each pixel with `LUT[pixel]`

Data layout:

- image pixels stored starting at address `0`
- LUT stored starting at address `width * height`
- kernel computes `lut_base`, loads pixel, indexes LUT, stores transformed result

Why it is interesting:

- shows alternate enhancement strategy on same GPU substrate
- separates adaptive policy on host from simple indexed execution on device
- good example of moving expensive nonlinear math off GPU and keeping device kernel simple

Tradeoffs:

- not same operation as assignment baseline, so it is extension only
- quality depends on global luminance model, which may underfit images with mixed local lighting
- requires extra memory for LUT, though only `256` entries
