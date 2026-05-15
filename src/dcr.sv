`default_nettype none
`timescale 1ns/1ns

// DEVICE CONTROL REGISTER
// > Used to configure high-level settings
// > In this minimal example, the DCR is used to configure the number of threads to run for the kernel
module dcr #(
    parameter THREAD_COUNT_BITS = 8
) (
    input wire clk,
    input wire reset,

    input wire device_control_write_enable,
    input wire [THREAD_COUNT_BITS-1:0] device_control_data,
    output wire [THREAD_COUNT_BITS-1:0] thread_count
);
    // Store device control data in dedicated register
    reg [THREAD_COUNT_BITS-1:0] device_control_register;
    assign thread_count = device_control_register;

    always @(posedge clk) begin
        if (reset) begin
            device_control_register <= {THREAD_COUNT_BITS{1'b0}};
        end else begin
            if (device_control_write_enable) begin 
                device_control_register <= device_control_data;
            end
        end
    end
endmodule
