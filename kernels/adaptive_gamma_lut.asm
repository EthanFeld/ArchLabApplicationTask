; Adaptive gamma LUT apply kernel.
; Host loads image pixels at address 0.
; Host loads 256-entry LUT at address width * height.

MUL R0, %blockIdx, %blockDim
ADD R0, R0, %threadIdx

CONST R1, #WIDTH
CONST R2, #HEIGHT
MUL R6, R1, R2         ; lut_base = width * height

LDR R3, R0             ; pixel
ADD R4, R6, R3         ; lut_base + pixel
LDR R5, R4             ; LUT[pixel]
STR R0, R5
RET
