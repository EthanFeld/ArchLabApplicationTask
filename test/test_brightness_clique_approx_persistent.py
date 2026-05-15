import cocotb
import os

from .helpers.memory import Memory
from .helpers.run import run_until_done
from .helpers.setup import setup
from tools.assembler import assemble_file
from tools.enhancement import build_brightness_clique_persistent_case


@cocotb.test()
async def test_brightness_clique_approx_persistent(dut):
    addr_bits = int(os.environ.get("GPU_DATA_MEM_ADDR_BITS", "16"))
    data_bits = int(os.environ.get("GPU_DATA_MEM_DATA_BITS", "16"))
    data_channels = int(os.environ.get("GPU_DATA_MEM_NUM_CHANNELS", "4"))
    program_channels = int(os.environ.get("GPU_PROGRAM_MEM_NUM_CHANNELS", "1"))

    case = build_brightness_clique_persistent_case(
        pixels=[10, 11, 12, 40, 42, 43, 120, 121, 122, 180],
        brightness=20,
        threshold=3,
        launch_threads=4,
    )

    program_memory = Memory(dut=dut, addr_bits=8, data_bits=16, channels=program_channels, name="program")
    program = assemble_file("kernels/brightness_clique_approx_persistent.asm", symbols=case["symbols"])

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

    actual = []
    for descriptor_index in range(case["result_count"]):
        base = case["descriptor_base"] + (descriptor_index * case["descriptor_stride"])
        run_length = data_memory.memory[base]
        value = data_memory.memory[base + case["value_offset"]]
        actual.extend([value] * run_length)

    assert actual == case["expected_pixels"]
    assert cycles > 0
