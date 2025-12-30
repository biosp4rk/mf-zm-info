import argparse
from enum import Flag, auto

from asm_writer import AsmWriter, AsmFormat
from rom import Rom, ROM_OFFSET
from symbols import Symbols
from thumb import ThumbInstruct


class DiffOpt(Flag):
    NONE = 0
    SKIP_PTRS = auto()
    SKIP_BLS = auto()
    DATA_ONLY = auto()


def diff_roms(rom_base: Rom, rom_new: Rom, options: DiffOpt) -> None:
    code_start = rom_base.code_start()
    code_end = rom_base.code_end()
    if DiffOpt.DATA_ONLY in options:
        start = rom_base.data_start()
    else:
        start = 0
        writer_base = AsmWriter.create(rom_base, Symbols(), set(), AsmFormat.DECOMP)
        writer_new = AsmWriter.create(rom_new, Symbols(), set(), AsmFormat.DECOMP)
    end = 0x800000
    for addr in range(start, end, 4):
        val_base = rom_base.read_32(addr)
        val_new = rom_new.read_32(addr)
        if DiffOpt.SKIP_PTRS in options and ROM_OFFSET <= val_base < ROM_OFFSET + end:
            continue
        if DiffOpt.SKIP_BLS in options and code_start <= addr < code_end:
            is_bl = False
            for i in [-2, 0, 2]:
                if (
                    rom_base.read_16(addr + i) >> 11 == 0b11110 and
                    rom_base.read_16(addr + i + 2) >> 11 == 0b11111
                ):
                    is_bl = True
                    break
            if is_bl:
                continue
        if val_base != val_new:
            # Print byte difference
            str_base = " ".join(f"{rom_base.read_8(addr + i):02X}" for i in range(4))
            str_new = " ".join(f"{rom_new.read_8(addr + i):02X}" for i in range(4))
            print(f"{addr:X}\t{str_base}\t{str_new}")
            if code_start <= addr < code_end:
                # Print instruction difference
                print_inst_diff(rom_base, rom_new, addr)
            input()
    print("Done")


def print_inst_diff(writer_base: AsmWriter, writer_new: AsmWriter, addr: int) -> None:
    for i in range(0, 4, 2):
        inst = ThumbInstruct(writer_base.rom, addr + i)
        str_base = writer_base.instruct_str(inst)
        inst = ThumbInstruct(writer_new.rom, addr + i)
        str_new = writer_base.instruct_str(inst)
        if str_base != str_new:
            print(f"{addr:X}\t{str_base}\t{str_new}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("rom_base", type=str)
    parser.add_argument("rom_new", type=str)
    parser.add_argument("-p", "--skip_ptrs", action="store_true", default=False)
    parser.add_argument("-b", "--skip_bls", action="store_true", default=False)
    parser.add_argument("-d", "--data_only", action="store_true", default=False)
    args = parser.parse_args()

    rom_base = Rom(args.rom_base)
    rom_new = Rom(args.rom_new)

    opt = DiffOpt.NONE
    if args.skip_ptrs:
        opt |= DiffOpt.SKIP_PTRS
    if args.skip_bls:
        opt |= DiffOpt.SKIP_BLS
    if args.data_only:
        opt |= DiffOpt.DATA_ONLY

    diff_roms(rom_base, rom_new, DiffOpt.NONE)
