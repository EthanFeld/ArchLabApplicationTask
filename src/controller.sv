`default_nettype none
`timescale 1ns/1ns

// MEMORY CONTROLLER
// > Receives memory requests from all cores
// > Throttles requests based on limited external memory bandwidth
// > Waits for responses from external memory and distributes them back to cores
// > Coalesces redundant reads that target the same address
module controller #(
    parameter ADDR_BITS = 8,
    parameter DATA_BITS = 16,
    parameter NUM_CONSUMERS = 4, // The number of consumers accessing memory through this controller
    parameter NUM_CHANNELS = 1,  // The number of concurrent channels available to send requests to global memory
    parameter WRITE_ENABLE = 1   // Whether this memory controller can write to memory (program memory is read-only)
) (
    input wire clk,
    input wire reset,

    // Consumer Interface (Fetchers / LSUs)
    input reg [NUM_CONSUMERS-1:0] consumer_read_valid,
    input reg [ADDR_BITS-1:0] consumer_read_address [NUM_CONSUMERS-1:0],
    output reg [NUM_CONSUMERS-1:0] consumer_read_ready,
    output reg [DATA_BITS-1:0] consumer_read_data [NUM_CONSUMERS-1:0],
    input reg [NUM_CONSUMERS-1:0] consumer_write_valid,
    input reg [ADDR_BITS-1:0] consumer_write_address [NUM_CONSUMERS-1:0],
    input reg [DATA_BITS-1:0] consumer_write_data [NUM_CONSUMERS-1:0],
    output reg [NUM_CONSUMERS-1:0] consumer_write_ready,

    // Memory Interface (Data / Program)
    output reg [NUM_CHANNELS-1:0] mem_read_valid,
    output reg [ADDR_BITS-1:0] mem_read_address [NUM_CHANNELS-1:0],
    input reg [NUM_CHANNELS-1:0] mem_read_ready,
    input reg [DATA_BITS-1:0] mem_read_data [NUM_CHANNELS-1:0],
    output reg [NUM_CHANNELS-1:0] mem_write_valid,
    output reg [ADDR_BITS-1:0] mem_write_address [NUM_CHANNELS-1:0],
    output reg [DATA_BITS-1:0] mem_write_data [NUM_CHANNELS-1:0],
    input reg [NUM_CHANNELS-1:0] mem_write_ready
);
    localparam IDLE = 3'b000,
        READ_WAITING = 3'b010,
        WRITE_WAITING = 3'b011;
    localparam CONSUMER_INDEX_BITS = (NUM_CONSUMERS <= 1) ? 1 : $clog2(NUM_CONSUMERS);

    // Keep track of state for each channel and which jobs each channel is handling.
    // For reads, one channel can fan one memory reply out to many consumers.
    reg [2:0] controller_state [NUM_CHANNELS-1:0];
    reg [CONSUMER_INDEX_BITS-1:0] current_consumer [NUM_CHANNELS-1:0];
    reg [NUM_CONSUMERS-1:0] read_consumer_mask [NUM_CHANNELS-1:0];
    reg [NUM_CONSUMERS-1:0] consumer_blocked;
    reg [NUM_CONSUMERS-1:0] reserved_consumers;
    reg [NUM_CONSUMERS-1:0] selected_read_consumers;
    integer i;
    integer j;
    integer k;
    reg request_found;

    always @(posedge clk) begin
        if (reset) begin
            mem_read_valid <= {NUM_CHANNELS{1'b0}};
            mem_write_valid <= {NUM_CHANNELS{1'b0}};
            consumer_read_ready <= {NUM_CONSUMERS{1'b0}};
            consumer_write_ready <= {NUM_CONSUMERS{1'b0}};
            consumer_blocked <= {NUM_CONSUMERS{1'b0}};

            for (i = 0; i < NUM_CHANNELS; i = i + 1) begin
                mem_read_address[i] <= {ADDR_BITS{1'b0}};
                mem_write_address[i] <= {ADDR_BITS{1'b0}};
                mem_write_data[i] <= {DATA_BITS{1'b0}};
                current_consumer[i] <= {CONSUMER_INDEX_BITS{1'b0}};
                read_consumer_mask[i] <= {NUM_CONSUMERS{1'b0}};
                controller_state[i] <= IDLE;
            end

            for (i = 0; i < NUM_CONSUMERS; i = i + 1) begin
                consumer_read_data[i] <= {DATA_BITS{1'b0}};
            end
        end else begin
            consumer_read_ready <= {NUM_CONSUMERS{1'b0}};
            consumer_write_ready <= {NUM_CONSUMERS{1'b0}};
            reserved_consumers = consumer_blocked;

            // Once consumer drops valid, its slot can be reused even if channel already moved on.
            for (j = 0; j < NUM_CONSUMERS; j = j + 1) begin
                if (!consumer_read_valid[j] && (!WRITE_ENABLE || !consumer_write_valid[j])) begin
                    consumer_blocked[j] <= 1'b0;
                    reserved_consumers[j] = 1'b0;
                end
            end

            // For each channel, we handle processing concurrently
            for (i = 0; i < NUM_CHANNELS; i = i + 1) begin
                case (controller_state[i])
                    IDLE: begin
                        // While idle, cycle through consumers looking for pending request.
                        // Reads can be coalesced when many consumers request same address.
                        request_found = 1'b0;
                        selected_read_consumers = {NUM_CONSUMERS{1'b0}};

                        for (j = 0; j < NUM_CONSUMERS; j = j + 1) begin
                            if (!request_found && consumer_read_valid[j] && !reserved_consumers[j]) begin
                                current_consumer[i] <= j;
                                selected_read_consumers[j] = 1'b1;

                                for (k = j + 1; k < NUM_CONSUMERS; k = k + 1) begin
                                    if (
                                        consumer_read_valid[k] &&
                                        !reserved_consumers[k] &&
                                        consumer_read_address[k] == consumer_read_address[j]
                                    ) begin
                                        selected_read_consumers[k] = 1'b1;
                                    end
                                end

                                for (k = 0; k < NUM_CONSUMERS; k = k + 1) begin
                                    if (selected_read_consumers[k]) begin
                                        consumer_blocked[k] <= 1'b1;
                                        reserved_consumers[k] = 1'b1;
                                    end
                                end

                                read_consumer_mask[i] <= selected_read_consumers;
                                mem_read_valid[i] <= 1'b1;
                                mem_read_address[i] <= consumer_read_address[j];
                                controller_state[i] <= READ_WAITING;
                                request_found = 1'b1;
                            end else if (
                                WRITE_ENABLE &&
                                !request_found &&
                                consumer_write_valid[j] &&
                                !reserved_consumers[j]
                            ) begin
                                current_consumer[i] <= j;
                                read_consumer_mask[i] <= {NUM_CONSUMERS{1'b0}};
                                consumer_blocked[j] <= 1'b1;
                                reserved_consumers[j] = 1'b1;

                                mem_write_valid[i] <= 1'b1;
                                mem_write_address[i] <= consumer_write_address[j];
                                mem_write_data[i] <= consumer_write_data[j];
                                controller_state[i] <= WRITE_WAITING;
                                request_found = 1'b1;
                            end
                        end
                    end
                    READ_WAITING: begin
                        // Wait for response from memory for pending read request
                        if (mem_read_ready[i]) begin
                            mem_read_valid[i] <= 1'b0;

                            for (j = 0; j < NUM_CONSUMERS; j = j + 1) begin
                                if (read_consumer_mask[i][j]) begin
                                    consumer_read_ready[j] <= 1'b1;
                                    consumer_read_data[j] <= mem_read_data[i];
                                end
                            end

                            read_consumer_mask[i] <= {NUM_CONSUMERS{1'b0}};
                            controller_state[i] <= IDLE;
                        end
                    end
                    WRITE_WAITING: begin
                        // Wait for response from memory for pending write request
                        if (mem_write_ready[i]) begin
                            mem_write_valid[i] <= 1'b0;
                            consumer_write_ready[current_consumer[i]] <= 1'b1;
                            controller_state[i] <= IDLE;
                        end
                    end
                endcase
            end
        end
    end
endmodule
