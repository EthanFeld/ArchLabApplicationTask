import cocotb
from cocotb.triggers import RisingEdge

from .helpers.memory import Memory
from .helpers.setup import setup


@cocotb.test()
async def test_program_fetch_coalescing(dut):
    # Two equal-sized blocks on two cores stay in lockstep.
    # Redundant-read coalescing should collapse duplicate instruction fetches.
    program_memory = Memory(dut=dut, addr_bits=8, data_bits=16, channels=1, name="program")
    program = [
        0b0101000011011110, # MUL R0, %blockIdx, %blockDim
        0b0011000000001111, # ADD R0, R0, %threadIdx
        0b1001000100000000, # CONST R1, #0
        0b1001001000001000, # CONST R2, #8
        0b1001001100010000, # CONST R3, #16
        0b0011010000010000, # ADD R4, R1, R0
        0b0111010001000000, # LDR R4, R4
        0b0011010100100000, # ADD R5, R2, R0
        0b0111010101010000, # LDR R5, R5
        0b0011011001000101, # ADD R6, R4, R5
        0b0011011100110000, # ADD R7, R3, R0
        0b1000000001110110, # STR R7, R6
        0b1111000000000000, # RET
    ]

    data_memory = Memory(dut=dut, addr_bits=8, data_bits=8, channels=4, name="data")
    data = [
        0, 1, 2, 3, 4, 5, 6, 7,
        0, 1, 2, 3, 4, 5, 6, 7,
    ]

    await setup(
        dut=dut,
        program_memory=program_memory,
        program=program,
        data_memory=data_memory,
        data=data,
        threads=8,
    )

    while int(str(dut.done.value), 2) != 1:
        data_memory.run()
        program_memory.run()
        await RisingEdge(dut.clk)

    expected_results = [a + b for a, b in zip(data[0:8], data[8:16])]
    assert data_memory.memory[16:24] == expected_results
    assert program_memory.read_transactions < len(program) * 2
