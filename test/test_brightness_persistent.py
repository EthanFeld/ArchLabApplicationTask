import cocotb
import os

from .helpers.memory import Memory
from .helpers.run import run_until_done
from .helpers.setup import setup
from tools.assembler import assemble_file
from tools.enhancement import build_brightness_persistent_case


@cocotb.test()
async def test_brightness_persistent(dut):
    addr_bits = int(os.environ.get("GPU_DATA_MEM_ADDR_BITS", "16"))
    data_bits = int(os.environ.get("GPU_DATA_MEM_DATA_BITS", "16"))
    data_channels = int(os.environ.get("GPU_DATA_MEM_NUM_CHANNELS", "4"))
    program_channels = int(os.environ.get("GPU_PROGRAM_MEM_NUM_CHANNELS", "1"))

    case = build_brightness_persistent_case(
        width=4,
        height=2,
        pixels=[0, 32, 127, 200, 220, 240, 250, 255],
        brightness=48,
        launch_threads=4,
    )

    program_memory = Memory(dut=dut, addr_bits=8, data_bits=16, channels=program_channels, name="program")
    program = assemble_file("kernels/brightness_persistent.asm", symbols=case["symbols"])

    data_memory = Memory(dut=dut, addr_bits=addr_bits, data_bits=data_bits, channels=data_channels, name="data")

    await setup(
        dut=dut,
        program_memory=program_memory,
        program=program,
        data_memory=data_memory,
        data=case["data"],
        threads=case["thread_count"],
    )

    cycles = await run_until_done(
        dut,
        data_memory=data_memory,
        program_memory=program_memory,
    )

    offset = case["output_offset"]
    actual = data_memory.memory[offset : offset + len(case["expected_pixels"])]
    assert actual == case["expected_pixels"]
    assert cycles > 0
