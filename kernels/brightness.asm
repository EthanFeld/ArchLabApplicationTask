; Brightness adjustment kernel for grayscale images.
; One thread handles one pixel in-place.
; Host loads grayscale pixels at data memory address 0.
; Uses SATADD to clamp directly to 255.

MUL R0, %blockIdx, %blockDim
ADD R0, R0, %threadIdx

CONST R1, #K

LDR R3, R0             ; pixel
SATADD R4, R3, R1      ; min(255, pixel + K)
STR R0, R4
RET
