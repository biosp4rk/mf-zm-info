import argparse

import argparse_utils as apu
from compress import decomp_rle
from rom import Rom


def compare_block_bg(rom_1: Rom, rom_2: Rom, addr_1: int, addr_2: int) -> None:
    width_1 = rom_1.read_8(addr_1)
    height_1 = rom_1.read_8(addr_1 + 1)
    width_2 = rom_2.read_8(addr_2)
    height_2 = rom_2.read_8(addr_2 + 1)
    if width_1 != width_2 or height_1 != height_2:
        print(f"Different dimensions: {width_1}, {height_1} and {width_2}, {height_2}")
    blocks_1, _ = decomp_rle(rom_1.data, addr_1 + 2)
    blocks_2, _ = decomp_rle(rom_2.data, addr_2 + 2)
    if len(blocks_1) != len(blocks_2):
        raise ValueError("Decompressed data lengths are different")
    if len(blocks_1) != width_1 * height_1 * 2:
        raise ValueError("Decompressed data length does not match room dimensions")
    for y in range(height_1):
        for x in range(width_1):
            i = (y * width_1 + x) * 2
            b1 = blocks_1[i] | (blocks_1[i + 1] << 8)
            b2 = blocks_2[i] | (blocks_2[i + 1] << 8)
            if b1 != b2:
                print(f"{x:X}, {y:X}: {b1:X} and {b2:X}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("data_type", type=str, choices=["block_bg"])
    apu.add_arg(parser, apu.ArgType.ROM_PATH, "rom_path_1")
    apu.add_arg(parser, apu.ArgType.ROM_PATH, "rom_path_2")
    apu.add_arg(parser, apu.ArgType.ADDR, "addr_1")
    apu.add_arg(parser, apu.ArgType.ADDR, "addr_2")
    
    args = parser.parse_args()
    rom_1 = apu.get_rom(args.rom_path_1)
    rom_2 = apu.get_rom(args.rom_path_2)
    addr_1 = apu.get_hex(args.addr_1)
    addr_2 = apu.get_hex(args.addr_2)

    if args.data_type == "block_bg":
        compare_block_bg(rom_1, rom_2, addr_1, addr_2)
