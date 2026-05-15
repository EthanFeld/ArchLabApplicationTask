; Persistent-thread brightness kernel with 4x loop unrolling.
; data[0] = loop count per launched thread
; data[1] = launch stride (total launched threads)
; data[2..] = pixel buffer padded to loop_count * stride * 4
;
; This keeps the launch fixed at hardware residency, then lets each thread
; process four grid-stride pixels per loop trip. It is still a normal
; tiny-gpu kernel, but it amortizes loop/dispatch overhead much better
; than one-thread-per-pixel and better than a 1x persistent loop.

MUL R0, %blockIdx, %blockDim
ADD R0, R0, %threadIdx

CONST R7, #0
LDR R5, R7             ; loop count per thread

CONST R6, #1
LDR R6, R6             ; launch stride

CONST R1, #K
CONST R2, #2           ; pixel data base
CONST R3, #1           ; decrement step

LOOP:
ADD R4, R2, R0
LDR R8, R4
SATADD R8, R8, R1
STR R4, R8
ADD R0, R0, R6

ADD R4, R2, R0
LDR R8, R4
SATADD R8, R8, R1
STR R4, R8
ADD R0, R0, R6

ADD R4, R2, R0
LDR R8, R4
SATADD R8, R8, R1
STR R4, R8
ADD R0, R0, R6

ADD R4, R2, R0
LDR R8, R4
SATADD R8, R8, R1
STR R4, R8
ADD R0, R0, R6

SUB R5, R5, R3
CMP R5, R7
BRp LOOP
RET
