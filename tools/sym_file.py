import argparse

import argparse_utils as apu
from constants import MAP_CODE, MAP_DATA, MAP_RAM
from function import all_functions
from info_entry import DataEntry, CodeEntry
from info_file_utils import get_info_file_from_json
from rom import Rom, ROM_OFFSET


def gen_sym_file(rom: Rom):
    # Get all function offsets and their pointers and pools
    func_addrs = []
    loaded_words = set()
    pool_sizes = []
    funcs = all_functions(rom)
    for func in funcs:
        func_addrs.append(func.start_addr)
        func_pools = func.get_data_pools()
        if len(func_pools) > 0:
            pool_sizes += func_pools
            for offset, size in func_pools:
                for i in range(0, size, 4):
                    word = rom.read_32(offset + i)
                    loaded_words.add(word)
    func_addrs += list(rom.arm_functions().keys())
    func_addrs.sort()

    # Get dictionaries with <addr, name>
    ram: list[DataEntry] = get_info_file_from_json(rom.game, MAP_RAM, rom.region)
    ram_dict = {r.addr: r.name for r in ram}
    code: list[CodeEntry] = get_info_file_from_json(rom.game, MAP_CODE, rom.region)
    code_dict = {r.addr: r.name for r in code}
    data: list[DataEntry] = get_info_file_from_json(rom.game, MAP_DATA, rom.region)
    data_dict = {r.addr: r.name for r in data}

    # Write to file
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
            name = ram_dict[word]
            lines.append(f"{word:08X} {name}")
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
            name = ram_dict[word]
            lines.append(f"{word:08X} {name}")
        else:
            lines.append(f";{word:08X}")
    lines.append("")

    # Code
    lines.append("; ROM code")
    for func_addr in func_addrs:
        word = func_addr + ROM_OFFSET
        if func_addr in code_dict:
            name = code_dict[func_addr]
            lines.append(f"{word:08X} {name}")
        else:
            lines.append(f";{word:08X}")
    lines.append("")

    # Data
    data_start = rom.data_start(True)
    data_end = rom.data_end(True)
    while words[j] < data_start:
        j += 1
    lines.append("; ROM data")
    while words[j] < data_end:
        word = words[j]
        j += 1
        key = word - ROM_OFFSET
        if key in data_dict:
            name = data_dict[key]
            lines.append(f"{word:08X} {name}")
        else:
            lines.append(f";{word:08X}")
    lines.append("")

    # Pools
    lines.append("; Pools")
    for offset, size in pool_sizes:
        off = offset + ROM_OFFSET
        lines.append(f"{off:08X} .dbl:{size:04X}")

    return lines


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    apu.add_arg(parser, apu.ArgType.ROM_PATH)
    parser.add_argument("out_path", type=str)

    args = parser.parse_args()
    rom = apu.get_rom(args.rom_path)
    
    lines = gen_sym_file(rom)
    with open(args.out_path, 'w') as f:
        for line in lines:
            f.write(f"{line}\n")
