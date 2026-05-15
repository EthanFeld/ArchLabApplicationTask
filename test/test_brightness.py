import json
import os
from pathlib import Path

import cocotb
from cocotb.triggers import RisingEdge

from .helpers.format import format_cycle
from .helpers.memory import Memory
from .helpers.setup import setup
from tools.assembler import assemble_file
from tools.enhancement import build_brightness_case

ROOT = Path(__file__).resolve().parents[1]


def _to_int(value) -> int:
    return int(str(value), 2)


@cocotb.test()
async def test_brightness(dut):
    case_path_env = os.environ.get("ENHANCEMENT_CASE_PATH")
    result_path_env = os.environ.get("ENHANCEMENT_RESULT_PATH")
    addr_bits = int(os.environ.get("GPU_DATA_MEM_ADDR_BITS", "8"))
    data_bits = int(os.environ.get("GPU_DATA_MEM_DATA_BITS", "8"))
    data_channels = int(os.environ.get("GPU_DATA_MEM_NUM_CHANNELS", "4"))
    program_channels = int(os.environ.get("GPU_PROGRAM_MEM_NUM_CHANNELS", "1"))
    trace = os.environ.get("ENHANCEMENT_TRACE", "0") == "1"

    if case_path_env:
        case_path = Path(case_path_env)
        result_path = Path(result_path_env) if result_path_env else None
        case = json.loads(case_path.read_text(encoding="utf-8"))
    else:
        result_path = None
        case = build_brightness_case(
            width=4,
            height=2,
            pixels=[0, 32, 127, 200, 220, 240, 250, 255],
            brightness=48,
        )

    width = int(case["width"])
    height = int(case["height"])
    data = [int(pixel) for pixel in case["data"]]
    expected_pixels = [int(pixel) for pixel in case["expected_pixels"]]
    kernel = case["kernel"]
    symbols = {key: int(value) for key, value in case.get("symbols", {}).items()}
    metadata = case.get("metadata", {})
    thread_count = int(case.get("thread_count", len(expected_pixels)))
    output_offset = int(case.get("output_offset", 0))
    result_layout = case.get("result_layout", "linear")
    result_count = int(case.get("result_count", thread_count))
    descriptor_base = int(case.get("descriptor_base", 0))
    descriptor_stride = int(case.get("descriptor_stride", 0))
    value_offset = int(case.get("value_offset", 0))

    assert len(expected_pixels) == width * height
    assert len(data) <= 2**addr_bits

    program_memory = Memory(dut=dut, addr_bits=8, data_bits=16, channels=program_channels, name="program")
    program = assemble_file(ROOT / "kernels" / kernel, symbols=symbols)

    data_memory = Memory(
        dut=dut,
        addr_bits=addr_bits,
        data_bits=data_bits,
        channels=data_channels,
        name="data",
    )

    await setup(
        dut=dut,
        program_memory=program_memory,
        program=program,
        data_memory=data_memory,
        data=data,
        threads=thread_count,
    )

    cycles = 0
    while _to_int(dut.done.value) != 1:
        data_memory.run()
        program_memory.run()

        if trace:
            await cocotb.triggers.ReadOnly()
            format_cycle(dut, cycles)

        await RisingEdge(dut.clk)
        cycles += 1

    if result_layout == "run_length_values":
        actual = []
        for descriptor_index in range(result_count):
            base = descriptor_base + (descriptor_index * descriptor_stride)
            run_length = int(data_memory.memory[base])
            value = int(data_memory.memory[base + value_offset])
            actual.extend([value] * run_length)
    else:
        actual = data_memory.memory[output_offset : output_offset + len(expected_pixels)]
    assert actual == expected_pixels

    if result_path is not None:
        result_path.write_text(
            json.dumps(
                {
                    "width": width,
                    "height": height,
                    "mode": case["mode"],
                    "cycles": cycles,
                    "pixels": actual,
                    "metadata": metadata,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
