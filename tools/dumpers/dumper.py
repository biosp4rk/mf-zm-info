import argparse

import argparse_utils as apu
from rom import Rom


def dump_bytes(
    rom: Rom,
    addr: int,
    length: int,
    size: int = 1,
    per_line: int = None,
    decimal: bool = False,
    commas: bool = False
):
    if size == 1:
        read_val = rom.read_8
    elif size == 2:
        read_val = rom.read_16
    elif size == 4:
        read_val = rom.read_32
    else:
        raise ValueError("Invalid byte size")

    if decimal:
        ft = "d"
    else:
        ft = f"0{size * 2}X"

    if per_line is None:
        per_line = 16 // size

    sep = ", " if commas else " "
    line_end = sep.rstrip()

    end = addr + length
    inc = per_line * size
    for i in range(addr, end, inc):
        j = min(i + inc, end)
        print(sep.join(f"{read_val(a):{ft}}" for a in range(i, j, size)) + line_end)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    apu.add_rom(parser)
    apu.add_addr(parser)
    parser.add_argument("length", type=str)
    parser.add_argument("-s", "--size", type=int,
        choices=[1, 2, 4], default=1)
    parser.add_argument("-l", "--per_line", type=int)
    parser.add_argument("-d", "--decimal", action="store_true")
    parser.add_argument("-c", "--commas", action="store_true")

    args = parser.parse_args()
    rom = args.rom_path
    addr = args.addr
    length = int(args.length, 16)
    dump_bytes(rom, addr, length, args.size, args.per_line, args.decimal, args.commas)
