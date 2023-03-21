import argparse
from typing import List

from constants import *
from function import Function
from game_info import GameInfo
from info_entry import PrimType, DataEntry, VarEntry
from rom import Rom, ROM_OFFSET
from symbols import Symbols, LabelType


def data_files(path: str, rom: Rom, info: GameInfo, labels: List[str]):
    for lab in labels:
        entry = info.get_data(lab)
        if not entry:
            raise ValueError(lab)
        addr = entry.addr
        size = entry.size(info.structs)
        dat = rom.read_bytes(addr, size)
        with open(path + f"{lab}.bin", "wb") as f:
            f.write(dat)


def unk_asm(rom: Rom, addr: int, count: int, per_line: int = 16) -> str:
    lines = []
    for i in range(0, count, per_line):
        row = min(per_line, count - i)
        vals = [rom.read8(addr + i + j) for j in range(row)]
        strs = ",".join(f"0x{v:02X}" for v in vals)
        lines.append(f".db {strs}")
    return "\n".join(lines)


def u8_asm(rom: Rom, entry: VarEntry, entry_addr: int, per_line: int = 16) -> str:
    count = entry.get_total_count()
    lines = []
    for i in range(0, count, per_line):
        row = min(per_line, count - i)
        vals = [rom.read8(entry_addr + i + j) for j in range(row)]
        strs = ",".join(f"0x{v:02X}" for v in vals)
        line = f".db {strs} ; {entry.label}"
        if count > 1:
            line += f" {i:02X}"
        lines.append(line)
    return "\n".join(lines)


def u16_asm(rom: Rom, entry: VarEntry, entry_addr: int, per_line: int = 8) -> str:
    count = entry.get_total_count()
    lines = []
    for i in range(0, count, per_line):
        row = min(per_line, count - i)
        vals = [rom.read16(entry_addr + (i + j) * 2) for j in range(row)]
        strs = ",".join(f"0x{v:04X}" for v in vals)
        line = f".dh {strs} ; {entry.label}"
        if count > 1:
            line += f" {i:02X}"
        lines.append(line)
    return "\n".join(lines)


def u32_asm(rom: Rom, entry: VarEntry, entry_addr: int, per_line: int = 4) -> str:
    count = entry.get_total_count()
    lines = []
    for i in range(0, count, per_line):
        row = min(per_line, count - i)
        vals = [rom.read32(entry_addr + (i + j) * 4) for j in range(row)]
        strs = ",".join(f"0x{v:08X}" for v in vals)
        line = f".dw {strs} ; {entry.label}"
        if count > 1:
            line += f" {i:02X}"
        lines.append(line)
    return "\n".join(lines)


def ptr_asm(
    rom: Rom,
    info: GameInfo,
    entry: VarEntry,
    entry_addr: int,
    per_line: int = 4
) -> str:
    count = entry.get_total_count()
    lines = []
    for i in range(0, count, per_line):
        row = min(per_line, count - i)
        strs = []
        for j in range(row):
            addr = entry_addr + (i + j) * 4
            val = rom.read32(addr)
            check = val
            if check >= ROM_OFFSET:
                check -= ROM_OFFSET
            ptr_entry = info.get_entry_by_addr(check)
            if ptr_entry is None:
                strs.append(f"0x{val:X}")
            else:
                strs.append(ptr_entry.label)
        vals = ",".join(strs)
        line = f".dw {vals} ; {entry.label}"
        if count > 1:
            line += f" {i:02X}"
        lines.append(line)
    return "\n".join(lines)


def data_asm(rom: Rom, info: GameInfo, entry: VarEntry, entry_addr: int):
    # check for pointer
    if entry.is_ptr():
        return ptr_asm(rom, info, entry, entry_addr)
    # check for struct
    prim = entry.primitive
    if prim == PrimType.Struct:
        count = entry.get_total_count()
        struct = info.get_struct(entry.struct_name)
        result = []
        for num in range(count):
            item_addr = entry_addr + struct.size * num
            addr = item_addr
            line = f"; {entry.label}"
            if count > 1:
                line += f" {num:02X}"
            result.append(line)
            for se in struct.vars:
                alignment = se.get_alignment(info.structs)
                var_addr = item_addr + se.offset
                diff = var_addr - addr
                if diff > 0:
                    if diff < alignment:
                        # close enough to align
                        result.append(f".align {alignment}")
                    else:
                        result.append(unk_asm(rom, addr, diff))
                result.append(data_asm(rom, info, se, var_addr))
                addr = var_addr + se.get_size(info.structs)
            # check for any remaining data
            end_addr = item_addr + struct.size
            diff = end_addr - addr
            if diff > 0:
                result.append(unk_asm(rom, addr, diff))
        return "\n".join(result)
    # assume integer type
    if prim == PrimType.U8 or prim == PrimType.S8 or prim == PrimType.Bool:
        return u8_asm(rom, entry, entry_addr)
    if prim == PrimType.U16 or prim == PrimType.S16:
        return u16_asm(rom, entry, entry_addr)
    if prim == PrimType.U32 or prim == PrimType.S32:
        return u32_asm(rom, entry, entry_addr)
    raise ValueError(prim)


def dump_data(rom: Rom, info: GameInfo, entry: DataEntry):
    # write file
    if entry.has_ptr(info.structs):
        # asm file
        asm = data_asm(rom, info, entry, entry.addr)
        path = f"{entry.label}.asm"
        with open(path, "w") as f:
            f.write(asm)
    else:
        # bin file
        size = entry.get_size(info.structs)
        data = rom.read_bytes(entry.addr, size)
        path = f"{entry.label}.asm"
        with open(path, "wb") as f:
            f.write(data)


def dump_funcs(path: str, rom: Rom, addrs: List[int]):
    info = GameInfo(rom.game, rom.region)
    syms = Symbols(info)

    # parse each function and get their symbols
    funcs = [Function(rom, addr, syms) for addr in addrs]
    used = {}
    for func in funcs:
        used.update(func.get_symbols())
    
    # get lines for labels and includes
    label_defs = []
    includes = []
    imports = []
    missing = []
    for addr, lab in sorted(used.items()):
        # check if in ram
        if (
            (addr >= 0x2000000 and addr < 0x2040000) or
            (addr >= 0x3000000 and addr < 0x3008000)
        ):
            label_defs.append(f".definelabel {lab},0x{addr:X}")
        else:
            addr -= ROM_OFFSET
            if addr < rom.code_end():
                # code
                includes.append(f".include {lab}.asm ; {addr:X}")
            else:
                # data
                imports.append(f".import {lab}.bin ; {addr:X}")
                # check if labeled
                entry = info.get_entry(lab)
                if entry is None:
                    missing.append(lab)

    sym_lines = []
    for lines in (label_defs, includes, imports):
        if len(lines) > 0:
            sym_lines += lines
            sym_lines.append("")
    if missing:
        sym_lines.append("; missing")
        for lab in missing:
            sym_lines.append(f"; {lab}")
    for line in sym_lines:
        print(line)

    # output functions as asm files
    for func in funcs:
        func_addr = func.start_addr + ROM_OFFSET
        label = syms.get_label(func_addr, LabelType.Code)
        lines = func.get_lines(False)
        with open(path + f"{label}.asm", "w") as f:
            for line in lines:
                f.write(line + "\n")


if __name__ == "__main__":
    import argparse_utils as apu
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    # funcs command
    subparser = subparsers.add_parser("funcs")
    apu.add_rom_path_arg(subparser)
    apu.add_addrs_arg(subparser)
    # data command
    subparser = subparsers.add_parser("data")
    apu.add_rom_path_arg(subparser)
    subparser.add_argument("labels", type=str)

    args = parser.parse_args()
    if args.command == "funcs":
        rom = apu.get_rom(args)
        addrs = apu.get_addrs(args)
        dump_funcs(rom, addrs)
    elif args.command == "data":
        rom = apu.get_rom(args)
        labels = args.labels.split(",")
        info = GameInfo(rom.game, rom.region)
        for label in labels:
            entry = info.get_data(label)
            if entry is None:
                raise ValueError(label)
            asm = data_asm(rom, info, entry, entry.addr)
            print(asm)
    else:
        parser.print_help()