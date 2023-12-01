import argparse
import math
from typing import List, Tuple

import png

import argparse_utils as apu
from compress import decomp_lz77
from rom import Rom

RGB = Tuple[int, int, int]


class Palette(object):
    
    def __init__(self, rows: int, rom: Rom = None, addr: int = None):
        assert rows >= 1
        self.colors = []
        if rom is not None or addr is not None:
            assert rom is not None and addr is not None
            for i in range(rows * 16):
                rgb = rom.read_16(addr + i * 2)
                r = rgb & 0x1F
                g = (rgb >> 5) & 0x1F
                b = (rgb >> 10)
                self.colors.append((r * 8, g * 8, b * 8))
        else:
            self.colors = [(0, 0, 0) for _ in range(rows * 16)]

    def __getitem__(self, key) -> RGB:
        return self.colors[key]

    @staticmethod
    def grayscale() -> "Palette":
        pal = Palette(1)
        for i in range(16):
            c = i * 16
            pal.colors[i] = (c, c, c)
        return pal        

    def get_row(self, row: int) -> List[RGB]:
        i = row * 16
        return self.colors[i:i+16]


class Gfx(object):

    def __init__(self,
        rom: Rom,
        addr: int,
        size: int = None,
        tile_width: int = 32
    ):
        if size is None:
            # compressed
            self.data, _ = decomp_lz77(rom.data, addr)
        else:
            # uncompressed
            assert size % 32 == 0
            self.data = rom.read_bytes(addr, size)
        self.set_tile_width(tile_width)

    def set_tile_width(self, tile_width: int):
        assert 1 <= tile_width <= 32
        self.tile_width = min(tile_width, self.get_num_tiles())

    def get_num_tiles(self) -> int:
        return len(self.data) // 32

    def get_at(self, x: int, y: int) -> int:
        i = (
            y // 8 * 32 * self.tile_width + # y tile
            y % 8 * 4 +                     # y pixel
            x // 8 * 32 +                   # x tile
            x % 8 // 2                      # x pixel
        )
        if i >= len(self.data):
            return 0
        if x % 2 == 0:
            return self.data[i] & 0xF
        else:
            return self.data[i] >> 4

    def draw(self, palette: Palette = None) -> png.Image:
        if palette is None:
            palette = Palette.grayscale()
        height = math.ceil(self.get_num_tiles() / self.tile_width) * 8
        width = self.tile_width * 8
        rows = []
        for y in range(height):
            row = []
            for x in range(width):
                i = self.get_at(x, y)
                row += palette[i]
            rows.append(row)
        return png.from_array(rows, "RGB")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    apu.add_arg(parser, apu.ArgType.ROM_PATH)
    apu.add_arg(parser, apu.ArgType.ADDR)
    parser.add_argument("-s", "--size", type=str)
    apu.add_arg(parser, apu.ArgType.ADDR, "-p", "--palette")
    parser.add_argument("path", type=str,
        help="Output path for png file")

    args = parser.parse_args()
    rom = apu.get_rom(args.rom_path)
    gfx_addr = apu.get_hex(args.addr)
    size = None
    if args.size:
        size = int(args.size, 16)
    pal = None
    if args.palette:
        pal_addr = apu.get_hex(args.palette)
        pal = Palette(1, rom, pal_addr)
    gfx = Gfx(rom, gfx_addr, size)
    image = gfx.draw(pal)
    image.save(args.path)
