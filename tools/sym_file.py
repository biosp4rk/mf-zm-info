import argparse
import sys
from typing import List

from constants import MAP_CODE, MAP_DATA, MAP_RAM
from function import Function
from info_entry import DataEntry, CodeEntry
from rom import Rom, ROM_OFFSET
from yaml_utils import load_yamls


def gen_sym_file(rom: Rom):
    # go through each function
    addr = rom.code_start()
    end = rom.code_end()
    arm_funcs = rom.arm_functions()
    region = rom.region
    
    # get all function offsets and their pointers and pools
    func_addrs = []
    loaded_words = set()
    pool_sizes = []
    while addr < end:
        func_addrs.append(addr)
        
        # skip dumping ARM functions
        if addr in arm_funcs:
            addr = arm_funcs[addr]
            continue

        # find any data pools in the function
        func = Function(rom, addr)
        func_pools = func.get_data_pools()
        if len(func_pools) > 0:
            pool_sizes += func_pools
            for offset, size in func_pools:
                for i in range(0, size, 4):
                    word = rom.read32(offset + i)
                    loaded_words.add(word)
        addr = func.end_addr

    # get dictionaries with <addr, label>
    ram: List[DataEntry] = load_yamls(rom.game, MAP_RAM, region)
    ram_dict = {r.addr: r.label for r in ram}
    code: List[CodeEntry] = load_yamls(rom.game, MAP_CODE, region)
    code_dict = {r.addr: r.label for r in code}
    data: List[DataEntry] = load_yamls(rom.game, MAP_DATA, region)
    data_dict = {r.addr: r.label for r in data}

    # write to file
    lines = []
    words = sorted(loaded_words)
    j = 0

    # WRAM [2]
    while words[j] < 0x2000000:
        j += 1
    lines.append("; WRAM")
    while words[j] < 0x2040000:
        word = words[j]
        j += 1
        if word in ram_dict:
            label = ram_dict[word]
            lines.append(f"{word:08X} {label}")
        else:
            lines.append(f";{word:08X}")
    lines.append("")

    # WRAM [3]
    while words[j] < 0x3000000:
        j += 1
    lines.append("; WRAM")
    while words[j] < 0x3008000:
        word = words[j]
        j += 1
        if word in ram_dict:
            label = ram_dict[word]
            lines.append(f"{word:08X} {label}")
        else:
            lines.append(f";{word:08X}")
    lines.append("")

    # code
    lines.append("; ROM code")
    for func_addr in func_addrs:
        word = func_addr + ROM_OFFSET
        if func_addr in code_dict:
            label = code_dict[func_addr]
            lines.append(f"{word:08X} {label}")
        else:
            lines.append(f";{word:08X}")
    lines.append("")

    # data
    data_start = rom.data_start(True)
    while words[j] < data_start:
        j += 1
    lines.append("; ROM data")
    data_end = rom.data_end(True)
    while words[j] < data_end:
        word = words[j]
        j += 1
        key = word - ROM_OFFSET
        if key in data_dict:
            label = data_dict[key]
            lines.append(f"{word:08X} {label}")
        else:
            lines.append(f";{word:08X}")
    lines.append("")

    # pools
    lines.append("; Pools")
    for offset, size in pool_sizes:
        off = offset + ROM_OFFSET
        lines.append(f"{off:08X} .dbl:{size:04X}")

    return lines


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("rom_path", type=str)
    parser.add_argument("out_path", type=str)
    args = parser.parse_args()

    if len(sys.argv) <= 2:
        parser.print_help()
        quit()

    # load rom
    rom = None
    try:
        rom = Rom(args.rom_path)
    except:
        print(f"Could not open rom at {args.rom_path}")
        quit()
    
    
    lines = gen_sym_file(rom)
    with open(args.out_path, 'w') as f:
        for line in lines:
            f.write(f"{line}\n")
