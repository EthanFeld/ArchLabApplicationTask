`default_nettype none
`timescale 1ns/1ns

// ARITHMETIC-LOGIC UNIT
// > Executes computations on register values
// > In this minimal implementation, the ALU supports the 4 basic arithmetic operations
// > Each thread in each core has it's own ALU
// > ADD, SUB, MUL, DIV instructions are all executed here
module alu #(
    parameter DATA_BITS = 8
) (
    input wire clk,
    input wire reset,
    input wire enable, // If current block has less threads then block size, some ALUs will be inactive

    input reg [2:0] core_state,

    input reg [2:0] decoded_alu_arithmetic_mux,
    input reg decoded_alu_output_mux,

    input reg [DATA_BITS-1:0] rs,
    input reg [DATA_BITS-1:0] rt,
    output wire [DATA_BITS-1:0] alu_out
);
    localparam ADD = 3'b000,
        SUB = 3'b001,
        MUL = 3'b010,
        DIV = 3'b011,
        SATADD = 3'b100;
    localparam SATURATION_BITS = (DATA_BITS < 8) ? DATA_BITS : 8;

    reg [DATA_BITS-1:0] alu_out_reg;
    wire [DATA_BITS:0] satadd_sum;
    wire [DATA_BITS:0] satadd_max;
    assign alu_out = alu_out_reg;
    assign satadd_sum = {1'b0, rs} + {1'b0, rt};
    assign satadd_max = {
        {(DATA_BITS + 1 - SATURATION_BITS){1'b0}},
        {SATURATION_BITS{1'b1}}
    };

    always @(posedge clk) begin 
        if (reset) begin 
            alu_out_reg <= {DATA_BITS{1'b0}};
        end else if (enable) begin
            // Calculate alu_out when core_state = EXECUTE
            if (core_state == 3'b101) begin 
                if (decoded_alu_output_mux == 1) begin 
                    // Set values to compare with NZP register in alu_out[2:0]
                    alu_out_reg <= {{(DATA_BITS - 3){1'b0}}, (rs < rt), (rs == rt), (rs > rt)};
                end else begin 
                    // Execute the specified arithmetic instruction
                    case (decoded_alu_arithmetic_mux)
                        ADD: begin 
                            alu_out_reg <= rs + rt;
                        end
                        SUB: begin 
                            alu_out_reg <= rs - rt;
                        end
                        MUL: begin 
                            alu_out_reg <= rs * rt;
                        end
                        DIV: begin 
                            alu_out_reg <= (rt == {DATA_BITS{1'b0}}) ? {DATA_BITS{1'b0}} : (rs / rt);
                        end
                        SATADD: begin
                            if (satadd_sum > satadd_max) begin
                                alu_out_reg <= satadd_max[DATA_BITS-1:0];
                            end else begin
                                alu_out_reg <= satadd_sum[DATA_BITS-1:0];
                            end
                        end
                        default: begin
                            alu_out_reg <= {DATA_BITS{1'b0}};
                        end
                    endcase
                end
            end
        end
    end
endmodule
