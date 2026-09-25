import argparse
from enum import Enum, auto

import argparse_utils as apu
from rom import Rom


class IntFormat(Enum):
    DEC = auto()
    HEX = auto()
    HEX_0X = auto()


class IntType(Enum):
    U8 = auto()
    U16 = auto()
    U32 = auto()
    S8 = auto()
    S16 = auto()
    S32 = auto()


def read_8(rom: Rom, addr: int, signed: bool) -> int:
    value = rom.read_8(addr)
    if signed and value > 0x80:
        value -= 0x100
    return value


def read_16(rom: Rom, addr: int, signed: bool) -> int:
    value = rom.read_16(addr)
    if signed and value > 0x8000:
        value -= 0x10000
    return value


def read_32(rom: Rom, addr: int, signed: bool) -> int:
    value = rom.read_32(addr)
    if signed and value > 0x8000_0000:
        value -= 0x1_0000_0000
    return value


def num_str(value: int, size: int, int_format: IntFormat) -> str:
    pre = "-" if value < 0 else ""
    if int_format == IntFormat.HEX_0X:
        pre += "0x"
    ft = "d" if int_format == IntFormat.DEC else f"0{size * 2}X"
    return f"{pre}{abs(value):{ft}}"


SIZES = {
    IntType.U8: 1,
    IntType.S8: 1,
    IntType.U16: 2,
    IntType.S16: 2,
    IntType.U32: 4,
    IntType.S32: 4,
}


READ_FUNCS = {
    IntType.U8: read_8,
    IntType.S8: read_8,
    IntType.U16: read_16,
    IntType.S16: read_16,
    IntType.U32: read_32,
    IntType.S32: read_32,
}


def dump_bytes(
    rom: Rom,
    addr: int,
    length: int,
    int_type = IntType.U8,
    int_format = IntFormat.HEX,
    per_line: int = None,
    commas: bool = False
):
    size = SIZES[int_type]
    read_val = READ_FUNCS[int_type]
    signed = int_type in {IntType.S8, IntType.S16, IntType.S32}

    if per_line is None:
        per_line = 16 // size

    sep = ", " if commas else " "
    line_end = sep.rstrip()

    end = addr + length
    inc = per_line * size
    for i in range(addr, end, inc):
        j = min(i + inc, end)
        print(
            sep.join(num_str(read_val(rom, a, signed), size, int_format)
            for a in range(i, j, size)) + line_end
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    apu.add_rom(parser)
    apu.add_addr(parser)
    parser.add_argument("length", type=str)
    parser.add_argument("-t", "--type", type=str,
        choices=["u8", "u16", "u32", "s8", "s16", "s32"], default="u8")
    parser.add_argument("-f", "--format", type = str,
        choices=["dec", "hex", "0x"], default="hex")
    parser.add_argument("-l", "--per_line", type=int)
    parser.add_argument("-c", "--commas", action="store_true")

    args = parser.parse_args()
    rom = args.rom_path
    addr = args.addr
    length = int(args.length, 16)
    int_type = IntType[args.type.upper()]
    int_format = {
        "dec": IntFormat.DEC,
        "hex": IntFormat.HEX,
        "0x": IntFormat.HEX_0X
    }[args.format.lower()]
    dump_bytes(rom, addr, length, int_type, int_format, args.per_line, args.commas)
