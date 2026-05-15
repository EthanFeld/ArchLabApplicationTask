from cocotb.triggers import RisingEdge


async def run_until_done(
    dut,
    *,
    data_memory,
    program_memory,
    max_cycles: int = 512,
) -> int:
    """Drive memory models until the DUT asserts `done` or times out.

    This is the common polling loop for small directed cocotb tests. The bound
    prevents silent hangs from looking like long-running simulations.
    """
    cycles = 0
    while int(str(dut.done.value), 2) != 1:
        if cycles >= max_cycles:
            raise AssertionError(f"Kernel did not assert done within {max_cycles} cycles")
        data_memory.run()
        program_memory.run()
        await RisingEdge(dut.clk)
        cycles += 1
    return cycles
