from __future__ import annotations

from pathlib import Path

REGISTER_IDS = {
    **{f"R{i}": i for i in range(13)},
    "%BLOCKIDX": 13,
    "%BLOCKDIM": 14,
    "%THREADIDX": 15,
}

ARITHMETIC_OPCODES = {
    "ADD": 0b0011,
    "SUB": 0b0100,
    "MUL": 0b0101,
    "DIV": 0b0110,
    "SATADD": 0b1010,
}


def _strip_comment(line: str) -> str:
    return line.split(";", 1)[0].strip()


def _split_label(line: str) -> tuple[list[str], str]:
    labels: list[str] = []
    remainder = line

    while ":" in remainder:
        label, possible_body = remainder.split(":", 1)
        if " " in label or "\t" in label:
            break

        label = label.strip()
        if label:
            labels.append(label)
        remainder = possible_body.strip()

    return labels, remainder


def _parse_register(token: str) -> int:
    key = token.strip().upper()
    if key not in REGISTER_IDS:
        raise ValueError(f"Unknown register token: {token}")
    return REGISTER_IDS[key]


def _parse_immediate(token: str, labels: dict[str, int], symbols: dict[str, int]) -> int:
    value_token = token.strip()
    if value_token.startswith("#"):
        value_token = value_token[1:]

    if value_token in labels:
        value = labels[value_token]
    elif value_token in symbols:
        value = symbols[value_token]
    else:
        value = int(value_token, 0)

    if not 0 <= value <= 0xFF:
        raise ValueError(f"Immediate out of 8-bit range: {value}")
    return value


def _instruction_body(lines: list[str]) -> tuple[dict[str, int], list[str]]:
    labels: dict[str, int] = {}
    instructions: list[str] = []
    pc = 0

    for raw_line in lines:
        line = _strip_comment(raw_line)
        if not line:
            continue

        new_labels, line = _split_label(line)
        for label in new_labels:
            labels[label] = pc

        if not line or line.startswith("."):
            continue

        instructions.append(line)
        pc += 1

    return labels, instructions


def _encode_instruction(line: str, labels: dict[str, int], symbols: dict[str, int]) -> int:
    parts = line.split(None, 1)
    mnemonic = parts[0].upper()
    operands = []
    if len(parts) > 1:
        operands = [operand.strip() for operand in parts[1].split(",") if operand.strip()]

    if mnemonic == "RET":
        return 0b1111 << 12

    if mnemonic == "CMP":
        rs, rt = (_parse_register(operand) for operand in operands)
        return (0b0010 << 12) | (rs << 4) | rt

    if mnemonic in ARITHMETIC_OPCODES:
        rd, rs, rt = (_parse_register(operand) for operand in operands)
        return (ARITHMETIC_OPCODES[mnemonic] << 12) | (rd << 8) | (rs << 4) | rt

    if mnemonic == "LDR":
        rd, rs = (_parse_register(operand) for operand in operands)
        return (0b0111 << 12) | (rd << 8) | (rs << 4)

    if mnemonic == "STR":
        rs, rt = (_parse_register(operand) for operand in operands)
        return (0b1000 << 12) | (rs << 4) | rt

    if mnemonic == "CONST":
        rd = _parse_register(operands[0])
        imm = _parse_immediate(operands[1], labels, symbols)
        return (0b1001 << 12) | (rd << 8) | imm

    if mnemonic.startswith("BR"):
        flags = mnemonic[2:] or "NZP"
        target_token = operands[0]

        if mnemonic == "BRNZP" and len(operands) == 2:
            flags = operands[0].upper()
            target_token = operands[1]

        nzp = 0
        if "N" in flags:
            nzp |= 0b100
        if "Z" in flags:
            nzp |= 0b010
        if "P" in flags:
            nzp |= 0b001

        imm = _parse_immediate(target_token, labels, symbols)
        return (0b0001 << 12) | (nzp << 9) | imm

    raise ValueError(f"Unsupported instruction: {line}")


def assemble_text(source: str, symbols: dict[str, int] | None = None) -> list[int]:
    symbol_table = symbols or {}
    labels, instructions = _instruction_body(source.splitlines())
    return [_encode_instruction(line, labels, symbol_table) for line in instructions]


def assemble_file(path: str | Path, symbols: dict[str, int] | None = None) -> list[int]:
    return assemble_text(Path(path).read_text(encoding="utf-8"), symbols=symbols)
