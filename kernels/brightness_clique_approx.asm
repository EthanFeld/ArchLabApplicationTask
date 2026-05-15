; Approximate brightness kernel over contiguous similarity cliques.
; data[0] = clique count
; data[1..] = [run_length, representative] pairs
;
; One thread handles one clique and brightens only the representative.
; Host expands each brightened representative back over the original run length.

MUL R0, %blockIdx, %blockDim
ADD R0, R0, %threadIdx

ADD R2, R0, R0         ; 2 * clique index
CONST R1, #2
ADD R2, R2, R1         ; representative address = 2 * idx + 2

CONST R3, #K
LDR R4, R2
SATADD R4, R4, R3
STR R2, R4
RET
