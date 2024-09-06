import argparse
from typing import Tuple

import argparse_utils as apu


MIN_MATCH_SIZE = 3
MIN_WINDOW_SIZE = 1

MAX_MATCH_SIZE = (1 << 4) - 1 + MIN_MATCH_SIZE
MAX_WINDOW_SIZE = (1 << 12) - 1 + MIN_WINDOW_SIZE


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
                window = ((input[idx] & 0xF) << 8) + input[idx + 1] + MIN_WINDOW_SIZE
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


def comp_lz77(input: bytes) -> bytes:
    # Assumes input stream starts at 0
    length = len(input)
    idx = 0
    longest_matches = find_longest_matches(input)

    # Write start of data
    output = bytearray()
    output.append(0x10)
    output.append(length & 0xFF)
    output.append((length >> 8) & 0xFF)
    output.append((length >> 16))

    while idx < length:
        # Get index of new compression flag
        flag = len(output)
        output.append(0)

        for i in range(8):
            # Find longest match at current position
            _match = longest_matches.get(idx)
            if _match is not None:
                # Compressed
                match_len, match_idx = _match
                match_offset = idx - match_idx - MIN_WINDOW_SIZE
                output.append(((match_len - MIN_MATCH_SIZE) << 4) | (match_offset >> 8))
                output.append(match_offset & 0xFF)
                output[flag] |= 0x80 >> i
                idx += match_len
            else:
                # Uncompressed
                output.append(input[idx])
                idx += 1

            # Check if at end
            if idx >= length:
                return bytes(output)
    
    raise Exception("LZ77 compression error")


def find_longest_matches(input: bytes) -> dict[int, tuple[int, int]]:
    length = len(input)
    triplets: dict[int, list[int]] = {}
    longest_matches: dict[int, tuple[int, int]] = {}

    for i in range(length - 2):
        # Get triplet at current position
        triplet = input[i] | (input[i + 1] << 8) | (input[i + 2] << 16)

        # Check if triplet has no match
        indexes = triplets.get(triplet)
        if indexes is None:
            triplets[triplet] = [i]
            continue

        window_start = max(i - MAX_WINDOW_SIZE, 0)
        max_size = min(MAX_MATCH_SIZE, length - i)
        longest_len = 0
        longest_idx = -1

        # Skip first index if one byte behind current position
        j = len(indexes) - 1
        if indexes[j] >= i - 1:
            j -= 1

        # Try each index to find the longest match
        while j >= 0:
            idx = indexes[j]
            # Stop if past window
            if idx < window_start:
                break

            # Find length of match
            match_len = MIN_MATCH_SIZE
            while match_len < max_size:
                if input[idx + match_len] != input[i + match_len]:
                    break
                match_len += 1
            
            # Update longest match
            if match_len > longest_len:
                longest_len = match_len
                longest_idx = idx

                # Stop looking if max size
                if longest_len == max_size:
                    break
            
            j -= 1

        indexes.append(i)
        if longest_len >= MIN_MATCH_SIZE:
            longest_matches[i] = (longest_len, longest_idx)

    return longest_matches


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
    parser = argparse.ArgumentParser()
    parser.add_argument("action", type=str, choices=["rle", "lz", "is-lz"])
    apu.add_arg(parser, apu.ArgType.ROM_PATH)
    apu.add_arg(parser, apu.ArgType.ADDR)

    args = parser.parse_args()
    rom = apu.get_rom(args.rom_path)
    addr = apu.get_hex(args.addr)

    if args.action == "rle":
        raw, size = decomp_rle(rom.data, addr)
        print(f"{len(raw):X}\t{size:X}")
    elif args.action == "lz":
        raw, size = decomp_lz77(rom.data, addr)
        print(f"{len(raw):X}\t{size:X}")
    if args.action == "is-lz":
        size = is_lz77(rom.data, addr)
        print(f"{size:X}")
