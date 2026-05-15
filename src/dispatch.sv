`default_nettype none
`timescale 1ns/1ns

// BLOCK DISPATCH
// > The GPU has one dispatch unit at the top level
// > Manages processing of threads and marks kernel execution as done
// > Sends off batches of threads in blocks to be executed by available compute cores
module dispatch #(
    parameter NUM_CORES = 2,
    parameter THREADS_PER_BLOCK = 4,
    parameter THREAD_COUNT_BITS = 8
) (
    input wire clk,
    input wire reset,
    input wire start,

    // Kernel Metadata
    input wire [THREAD_COUNT_BITS-1:0] thread_count,

    // Core States
    input reg [NUM_CORES-1:0] core_done,
    output reg [NUM_CORES-1:0] core_start,
    output reg [NUM_CORES-1:0] core_reset,
    output reg [THREAD_COUNT_BITS-1:0] core_block_id [NUM_CORES-1:0],
    output reg [$clog2(THREADS_PER_BLOCK):0] core_thread_count [NUM_CORES-1:0],

    // Kernel Execution
    output reg done
);
    // Calculate the total number of blocks based on total threads & threads per block
    wire [THREAD_COUNT_BITS-1:0] total_blocks;
    assign total_blocks = (thread_count + THREADS_PER_BLOCK - 1) / THREADS_PER_BLOCK;

    // Keep track of how many blocks have been processed
    reg [THREAD_COUNT_BITS-1:0] blocks_dispatched; // How many blocks have been sent to cores?
    reg [THREAD_COUNT_BITS-1:0] blocks_done; // How many blocks have finished processing?
    reg start_execution; // EDA: Unimportant hack used because of EDA tooling
    reg [THREAD_COUNT_BITS-1:0] next_blocks_dispatched;
    reg [THREAD_COUNT_BITS-1:0] next_blocks_done;
    reg [NUM_CORES-1:0] next_core_start;
    reg [NUM_CORES-1:0] next_core_reset;
    reg [THREAD_COUNT_BITS-1:0] next_core_block_id [NUM_CORES-1:0];
    reg [$clog2(THREADS_PER_BLOCK):0] next_core_thread_count [NUM_CORES-1:0];
    integer i;

    always @(posedge clk) begin
        if (reset) begin
            done <= 0;
            blocks_dispatched <= {THREAD_COUNT_BITS{1'b0}};
            blocks_done <= {THREAD_COUNT_BITS{1'b0}};
            start_execution <= 0;

            for (i = 0; i < NUM_CORES; i = i + 1) begin
                core_start[i] <= 0;
                core_reset[i] <= 1;
                core_block_id[i] <= 0;
                core_thread_count[i] <= THREADS_PER_BLOCK;
            end
        end else if (start) begin    
            next_blocks_dispatched = blocks_dispatched;
            next_blocks_done = blocks_done;
            next_core_start = core_start;
            next_core_reset = core_reset;
            for (i = 0; i < NUM_CORES; i = i + 1) begin
                next_core_block_id[i] = core_block_id[i];
                next_core_thread_count[i] = core_thread_count[i];
            end

            // EDA: Indirect way to get @(posedge start) without driving from 2 different clocks
            if (!start_execution) begin 
                start_execution <= 1;
                for (i = 0; i < NUM_CORES; i = i + 1) begin
                    next_core_reset[i] = 1;
                end
            end

            for (i = 0; i < NUM_CORES; i = i + 1) begin
                if (next_core_reset[i]) begin 
                    next_core_reset[i] = 0;

                    // If this core was just reset, check if there are more blocks to be dispatched
                    if (next_blocks_dispatched < total_blocks) begin 
                        next_core_start[i] = 1;
                        next_core_block_id[i] = next_blocks_dispatched;
                        next_core_thread_count[i] = (next_blocks_dispatched == total_blocks - 1) 
                            ? thread_count - (next_blocks_dispatched * THREADS_PER_BLOCK)
                            : THREADS_PER_BLOCK;

                        next_blocks_dispatched = next_blocks_dispatched + 1'b1;
                    end
                end
            end

            for (i = 0; i < NUM_CORES; i = i + 1) begin
                if (core_start[i] && core_done[i]) begin
                    // If a core just finished executing it's current block, reset it
                    next_core_reset[i] = 1;
                    next_core_start[i] = 0;
                    next_blocks_done = next_blocks_done + 1'b1;
                end
            end

            if (next_blocks_done == total_blocks) begin 
                done <= 1;
            end

            blocks_dispatched <= next_blocks_dispatched;
            blocks_done <= next_blocks_done;
            core_start <= next_core_start;
            core_reset <= next_core_reset;
            for (i = 0; i < NUM_CORES; i = i + 1) begin
                core_block_id[i] <= next_core_block_id[i];
                core_thread_count[i] <= next_core_thread_count[i];
            end
        end
    end
endmodule
