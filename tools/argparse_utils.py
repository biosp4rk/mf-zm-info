from argparse import ArgumentParser
from enum import Enum, auto
from typing import List

from rom import Rom


class ArgType(Enum):
    ROM_PATH = auto()
    ADDR = auto()
    ADDR_LIST = auto()


ARG_INFO = {
    ArgType.ROM_PATH: (str, "Path to a GBA ROM file"),
    ArgType.ADDR: (str, "Hex address"),
    ArgType.ADDR_LIST: (str, "Comma separated hex addresses"),
}


def add_arg(parser: ArgumentParser, arg_type: ArgType, *name_or_flags: str):
    if len(name_or_flags) == 0:
        name_or_flags = (arg_type.name.lower(),)
    type, help = ARG_INFO[arg_type]
    parser.add_argument(*name_or_flags, type=type, help=help)


def get_rom(rom_path: str) -> Rom:
    try:
        return Rom(rom_path)
    except:
        raise ValueError(f"Could not open rom at {rom_path}")


def get_hex(hex_str: str) -> int:
    try:
        return int(hex_str, 16)
    except:
        raise ValueError(f"Invalid hex address {hex_str}")


def get_hex_list(hex_list: str) -> List[int]:
    hex_strs = hex_list.split(",")
    try:
        return [int(a, 16) for a in hex_strs]
    except:
        raise ValueError(f"Invalid hex address in {hex_strs}")
