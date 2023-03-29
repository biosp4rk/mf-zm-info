import argparse
import codecs
import os
from typing import List

from constants import *
from function import Function
from game_info import GameInfo
from info_entry import PrimType, DataEntry, VarEntry
from rom import Rom, ROM_OFFSET
from symbols import Symbols, LabelType


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


def sjis_asm(rom: Rom, addr: int, count: int):
    chars = rom.read_bytes(addr, count)
    chars = bytes(c if c != 0 else 0x7E for c in chars)
    return codecs.decode(chars, "shift_jis")


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


def dump_data(path: str, rom: Rom, info: GameInfo, entry: DataEntry):
    # write file
    if entry.has_ptr(info.structs):
        # asm file
        asm = data_asm(rom, info, entry, entry.addr)
        fp = os.path.join(path, f"{entry.label}.asm")
        with open(fp, "w") as f:
            f.write(asm)
    else:
        # bin file
        size = entry.get_size(info.structs)
        data = rom.read_bytes(entry.addr, size)
        fp = os.path.join(path, f"{entry.label}.bin")
        with open(fp, "wb") as f:
            f.write(data)


def dump_funcs(path: str, rom: Rom, addrs: List[int]):
    info = GameInfo(rom.game, rom.region)
    syms = Symbols(info)

    # parse each function and get their symbols
    funcs = [Function(rom, addr, syms) for addr in addrs]
    used = {}
    for func in funcs:
        used.update(func.get_symbols())
    
    if not os.path.exists(path):
        os.makedirs(path)

    # get lines for labels and includes
    ram_defs = []
    code_defs = []
    data_defs = []
    missing = []
    code_end = rom.code_end(True)
    for addr, lab in sorted(used.items()):
        # check if in ram
        if (
            (addr >= 0x2000000 and addr < 0x2040000) or
            (addr >= 0x3000000 and addr < 0x3008000)
        ):
            ram_defs.append((lab, addr))
        else:
            if addr < code_end:
                code_defs.append((lab, addr))
            else:
                data_defs.append((lab, addr))
        # check if labeled
        entry = info.get_entry(lab)
        if entry is None:
            missing.append(lab)

    # output symbols
    sym_lines = []
    for defs in (ram_defs, code_defs, data_defs):
        if len(defs) > 0:
            for lab, addr in defs:
                sym_lines.append(f".definelabel {lab},0x{addr:X}")
            sym_lines.append("")    
    if missing:
        sym_lines.append("; missing")
        for lab in missing:
            sym_lines.append(f"; {lab}")
    fp = os.path.join(path, "symbols.asm")
    with open(fp, "w") as f:
        for line in sym_lines:
            f.write(line + "\n")

    # output functions as asm files
    for func in funcs:
        func_addr = func.start_addr + ROM_OFFSET
        label = syms.get_label(func_addr, LabelType.Code)
        lines = func.get_lines(False)
        fp = os.path.join(path, f"{label}.asm")
        with open(fp, "w") as f:
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
    # sjis command
    subparser = subparsers.add_parser("sjis")
    apu.add_rom_path_arg(subparser)
    apu.add_addr_arg(subparser)
    subparser.add_argument("count", type=str)

    args = parser.parse_args()
    if args.command == "funcs":
        rom = apu.get_rom(args)
        addrs = apu.get_addrs(args)
        dump_funcs("_asm", rom, addrs)
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
    elif args.command == "sjis":
        rom = apu.get_rom(args)
        addr = apu.get_addr(args)
        count = int(args.count, 16)
        print(sjis_asm(rom, addr, count))
    else:
        parser.print_help()