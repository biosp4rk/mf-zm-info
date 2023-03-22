import argparse
from typing import Tuple

from rom import Rom

MIN_MATCH_SIZE = 3
MAX_MATCH_SIZE = 18
MAX_WINDOW_SIZE = 0x1000


def decomp_rle(input: bytes, idx: int) -> Tuple[bytes, int]:
    src_start = idx
    passes = []
    half = None
    # for each pass
    for p in range(2):
        if p == 1:
            half = len(passes)
        num_bytes = input[idx]
        idx += 1
        while True:
            amount = None
            compare = None
            if num_bytes == 1:
                amount = input[idx]
                compare = 0x80
            else:
                # num_bytes == 2
                amount = (input[idx] << 8) | input[idx + 1]
                compare = 0x8000
            idx += num_bytes

            if amount == 0:
                break

            if (amount & compare) != 0:
                # compressed
                amount %= compare
                val = input[idx]
                idx += 1
                while amount > 0:
                    passes.append(val)
                    amount -= 1
            else:
                # uncompressed
                while amount > 0:
                    passes.append(input[idx])
                    idx +=1
                    amount -=1
    
    # each pass must be equal length
    if len(passes) != half * 2:
        raise ValueError()
    
    # combine passes to get output
    out_list = bytearray()
    for i in range(half):
        out_list.append(passes[i])
        out_list.append(passes[half + i])
    
    # return bytes and compressed size
    comp_size = idx - src_start
    return bytes(out_list), comp_size


def decomp_lz77(input: bytes, idx: int) -> Tuple[bytes, int]:
    # check for 0x10 flag
    if input[idx] != 0x10:
        raise ValueError("Missing 0x10 flag")

    # get length of decompressed data
    remain = input[idx + 1] | (input[idx + 2] << 8) | (input[idx + 3] << 16)
    output = bytearray([0] * remain)

    # check for valid data size
    if remain < 32 or remain % 32 != 0:
        raise ValueError("Invalid data size")

    start = idx
    idx += 4
    dst = 0

    # decompress
    while (True):
        cflag = input[idx]
        idx += 1

        for _ in range(8):
            if (cflag & 0x80) == 0:
                # uncompressed
                output[dst] = input[idx]
                idx += 1
                dst += 1
                remain -= 1
            else:
                # compressed
                amount_to_copy = (input[idx] >> 4) + MIN_MATCH_SIZE
                window = ((input[idx] & 0xF) << 8) + input[idx + 1] + 1
                idx += 2
                remain -= amount_to_copy
                
                for _ in range(amount_to_copy):
                    output[dst] = output[dst - window]
                    dst += 1

            if remain <= 0:
                if remain < 0:
                    raise ValueError("Too many bytes copied at end")
                comp_size = idx - start
                return bytes(output), comp_size
            cflag <<= 1


def is_lz77(input: bytes, idx: int) -> int:
    # check for 0x10 flag
    if input[idx] != 0x10:
        return -1

    # get length of decompressed data
    remain = input[idx + 1] | (input[idx + 2] << 8) | (input[idx + 3] << 16)

    # check for valid data size
    if remain < 32 or remain % 32 != 0:
        return -1

    start = idx
    idx += 4
    dst = 0

    # decompress
    while (True):
        cflag = input[idx]
        idx += 1

        for _ in range(8):
            if (cflag & 0x80) == 0:
                # uncompressed
                idx += 1
                dst += 1
                remain -= 1
            else:
                # compressed
                amount_to_copy = (input[idx] >> 4) + MIN_MATCH_SIZE
                window = ((input[idx] & 0xF) << 8) + input[idx + 1] + 1
                idx += 2
                remain -= amount_to_copy
                
                if dst - window < 0:
                    return -1
                dst += amount_to_copy

            if remain <= 0:
                if remain < 0:
                    return -1
                # return compressed length
                return idx - start
            cflag <<= 1


if __name__ == "__main__":
    import argparse_utils as apu
    parser = argparse.ArgumentParser()
    parser.add_argument("action", type=str, choices=["rle", "lz", "is-lz"])
    apu.add_rom_path_arg(parser)
    apu.add_addr_arg(parser)

    args = parser.parse_args()
    rom = apu.get_rom(args)
    addr = apu.get_addr(args)

    if args.action == "rle":
        raw, size = decomp_rle(rom.data, addr)
        print(f"{len(raw):X}\t{size:X}")
    elif args.action == "lz":
        raw, size = decomp_lz77(rom.data, addr)
        print(f"{len(raw):X}\t{size:X}")
    if args.action == "is-lz":
        size = is_lz77(rom.data, addr)
        print(f"{size:X}")
