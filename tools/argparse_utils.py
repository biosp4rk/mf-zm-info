import argparse
from typing import List

from rom import Rom


def add_rom_path_arg(parser: argparse.ArgumentParser):
    parser.add_argument("rom_path", type=str,
        help="Path to GBA ROM file")


def add_addr_arg(parser: argparse.ArgumentParser):
    parser.add_argument("addr", type=str,
        help="Hex address")


def add_addrs_arg(parser: argparse.ArgumentParser):
    parser.add_argument("addrs", type=str,
        help="Comma separated hex addresses")


def get_rom(args: argparse.Namespace) -> Rom:
    try:
        return Rom(args.rom_path)
    except:
        raise ValueError(f"Could not open rom at {args.rom_path}")


def get_addr(args: argparse.Namespace) -> int:
    try:
        return int(args.addr, 16)
    except:
        raise ValueError(f"Invalid hex address {args.addr}")


def get_addrs(args: argparse.Namespace) -> List[int]:
    addr_strs = args.addrs.split(",")
    try:
        return [int(a, 16) for a in addr_strs]
    except:
        raise ValueError(f"Invalid hex address in {args.addr}")
