import argparse
from typing import TextIO

from constants import GAMES, REGIONS, MAP_TYPES
import info_file_utils as ifu


class SymEntry:
    def __init__(self, addr: int, label: str, file: str = None):
        self.file = file
        self.addr = addr
        self.label = label

    def __str__(self) -> str:
        items = [f"{self.addr:X}", self.label]
        if self.file:
            items.append(self.file)
        return "\t".join(items)


def parse_linker_map(map_path: str) -> None:
    ram_entries = []
    code_entries = []
    data_entries = []
    with open(map_path) as f:
        # read until memory map reached
        for line in f:
            if "memory map" in line:
                break
        # read until first section reached
        for line in f:
            tokens = [t for t in line.split()]
            if len(tokens) == 0:
                continue
            if tokens[0] == "ewram":
                break
        # parse ewram section
        ram_entries += parse_ram(f, "iwram")
        # parse iwram section
        ram_entries += parse_ram(f, "rom")
        # parse rom
        sym_file = None
        sym_type = None
        for line in f:
            tokens = [t for t in line.split()]
            if len(tokens) == 0:
                continue
            first = tokens[0]
            if first.startswith("."):
                continue
            if first.startswith("OUTPUT("):
                break
            if len(tokens) == 1:
                i = first.rindex("(")
                sym_file = first[:i].replace(".o", "")
                sym_type = first[i+1:-1]
            elif len(tokens) == 2:
                if not first.startswith("0x"):
                    continue
                addr = int(first, 16)
                label = tokens[1]
                entry = SymEntry(addr, label, sym_file)
                if sym_type == ".text":
                    code_entries.append(entry)
                elif sym_type == ".rodata":
                    data_entries.append(entry)
                else:
                    raise ValueError(f"Invalid symbol type {sym_type}")
        return ram_entries, code_entries, data_entries


def parse_ram(f: TextIO, next_section: str) -> list[SymEntry]:
    entries = []
    for line in f:
        tokens = [t for t in line.split()]
        if len(tokens) == 0:
            continue
        if tokens[0] == next_section:
            break
        if len(tokens) == 4 and tokens[-1] == ".":
            addr = int(tokens[0], 16)
            label = tokens[1]
            entry = SymEntry(addr, label)
            entries.append(entry)
    return entries


def update_info_files(game: str) -> None:
    for map_type in MAP_TYPES:    
        paths = ifu.find_yaml_files(game, map_type)
        ylists = ifu.load_yaml_files(paths)
        for path, ylist in zip(paths, ylists):
            #name = os.path.basename(path)
            #print(f"Checking {game} {map_type} {name}")
            # TODO
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("map_path", type=str, help="Path to linker map file")
    parser.add_argument("game", type=str, choices=GAMES, help="Game abbreviation")
    parser.add_argument("region", type=str, choices=REGIONS, help="Region abbreviation")
    
    args = parser.parse_args()
    r, c, d = parse_linker_map(args.map_path)
    for e in d:
        print(e)
