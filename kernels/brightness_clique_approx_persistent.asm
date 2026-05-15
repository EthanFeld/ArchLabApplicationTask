; Persistent approximate brightness kernel over similarity cliques.
; data[0] = iteration count per launched thread
; data[1] = launch stride
; data[2] = actual clique count
; data[3..] = [run_length, representative] pairs, padded with zero-length cliques
;
; One launched thread processes a grid-stride stream of cliques.
; Only representative values are brightened; host expands each run afterward.

MUL R0, %blockIdx, %blockDim
ADD R0, R0, %threadIdx

CONST R7, #0
LDR R5, R7             ; loop count per thread

CONST R6, #1
LDR R6, R6             ; launch stride

CONST R1, #K
CONST R2, #3           ; descriptor base
CONST R3, #1           ; decrement step

LOOP:
ADD R4, R0, R0         ; 2 * clique index
ADD R4, R4, R2         ; descriptor base + 2 * idx
ADD R8, R4, R3         ; representative address
LDR R9, R8
SATADD R9, R9, R1
STR R8, R9
ADD R0, R0, R6

SUB R5, R5, R3
CMP R5, R7
BRp LOOP
RET
