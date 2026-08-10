from argparse import ArgumentParser, ArgumentTypeError

from rom import Rom


def rom_arg(s: str) -> Rom:
    try:
        return Rom(s)
    except Exception:
        raise ArgumentTypeError(f"Could not open rom at {s}")


def hex_arg(s: str) -> int:
    try:
        return int(s, 16)
    except ValueError:
        raise ArgumentTypeError(f"Invalid hex address {s}")


def hex_list_arg(s: str) -> list[int]:
    try:
        return [int(a, 16) for a in s.split(",")]
    except ValueError:
        raise ArgumentTypeError(f"Invalid hex address in {s}")


def add_rom(parser: ArgumentParser, *name_or_flags: str):
    parser.add_argument(*(name_or_flags or ("rom_path",)), type=rom_arg,
        help="Path to a GBA ROM file")


def add_addr(parser: ArgumentParser, *name_or_flags: str):
    parser.add_argument(*(name_or_flags or ("addr",)), type=hex_arg,
        help="Hex address")


def add_addr_list(parser: ArgumentParser, *name_or_flags: str):
    parser.add_argument(*(name_or_flags or ("addr_list",)), type=hex_list_arg,
        help="Comma separated hex addresses")
