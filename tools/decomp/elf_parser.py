import argparse
from enum import Enum

from constants import GAMES, REGIONS, MAP_TYPES
import info_file_utils as ifu


def update_info_files(game: str) -> None:
    for map_type in MAP_TYPES:    
        paths = ifu.find_yaml_files(game, map_type)
        ylists = ifu.load_yaml_files(paths)
        for path, ylist in zip(paths, ylists):
            #name = os.path.basename(path)
            #print(f"Checking {game} {map_type} {name}")
            # TODO
            pass


class ElfType(Enum):
    NOTYPE = 0
    SECTION = 1
    FILE = 2
    FUNC = 3
    OBJECT = 4


class ElfBind(Enum):
    LOCAL = 0
    GLOBAL = 1


class ElfSym:
    # ndx
    # ABS: constants
    # 1: ewram
    # 2: iwram
    # 3: rom (code)
    # 4: rodata
    def __init__(self,
        value: int,
        size: int,
        kind: ElfType,
        bind: ElfBind,
        ndx: int,
        name: str
    ):
        self.value = value
        self.size = size
        self.kind = kind
        self.bind = bind
        self.ndx = ndx
        self.name = name

    def __str__(self) -> str:
        return "\t".join([
            f"{self.value:08X}",
            f"{self.size:X}",
            self.kind.name,
            self.bind.name,
            str(self.ndx),
            self.name
        ])


def parse_elf_file(elf_path: str, remove_notype_locals: bool = True) -> list[ElfSym]:
    entries: list[ElfSym] = []
    with open(elf_path) as f:
        for line in f:
            entry = parse_elf_line(line)
            if entry is not None:
                entries.append(entry)
    if remove_notype_locals:
        entries = [e for e in entries if e.kind != ElfType.NOTYPE or e.bind != ElfBind.LOCAL]
    return entries


def parse_elf_line(line: str) -> ElfSym:
    items = line.split()
    if len(items) != 8:
        return None
    num = items[0]
    if not num[:-1].isdigit() or not num.endswith(":"):
        return None
    value = int(items[1], 16)
    size_str = items[2]
    base = 16 if size_str.startswith("0x") else 10
    size = int(size_str, base)
    kind = ElfType[items[3]]
    bind = ElfBind[items[4]]
    ndx_str = items[6]
    ndx = -1 if ndx_str == "ABS" else int(ndx_str)
    name = items[7]
    return ElfSym(value, size, kind, bind, ndx, name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("map_path", type=str, help="Path to linker map file")
    parser.add_argument("game", type=str, choices=GAMES, help="Game abbreviation")
    parser.add_argument("region", type=str, choices=REGIONS, help="Region abbreviation")
    
    args = parser.parse_args()
    entries = parse_elf_file(args.map_path)
    entries.sort(key=lambda e: e.value)
    for entry in entries:
        if entry.kind == ElfType.NOTYPE and entry.bind == ElfBind.LOCAL:
            continue
        print(entry)
