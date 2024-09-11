import argparse
from enum import Enum
import heapq
from typing import Tuple

import argparse_utils as apu


MIN_MATCH_SIZE = 3
MIN_WINDOW_SIZE = 1

MAX_MATCH_SIZE = (1 << 4) - 1 + MIN_MATCH_SIZE
MAX_WINDOW_SIZE = (1 << 12) - 1 + MIN_WINDOW_SIZE


class LzCompMethod(Enum):
    FAST = 0
    OPTIMAL = 1


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
    if remain == 0:
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


def is_lz77(input: bytes, idx: int) -> int:
    # check for 0x10 flag
    if input[idx] != 0x10:
        return -1

    # get length of decompressed data
    remain = input[idx + 1] | (input[idx + 2] << 8) | (input[idx + 3] << 16)

    # check for valid data size
    if remain == 0:
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


def comp_lz77(input: bytes, method: LzCompMethod = LzCompMethod.FAST) -> bytes:
    if method == LzCompMethod.FAST:
        return _comp_lz77_fast(input)
    elif method == LzCompMethod.OPTIMAL:
        return _comp_lz77_optimal(input)


def _comp_lz77_fast(input: bytes) -> bytes:
    """LZ77 compresses data by greedily selecting the longest match at each step."""
    # Assumes input stream starts at 0
    length = len(input)
    idx = 0
    longest_matches = _find_longest_matches(input)

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
                match_idx, match_len = _match
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


def _comp_lz77_optimal(input: bytes) -> bytes:
    """LZ77 compresses data by finding the optimal sequence of matches."""
    # Assumes input stream starts at 0
    length = len(input)
    idx = 0
    flag_counter = 8
    flag_idx = -1

    longest_matches = _find_longest_matches(input)
    path = _find_best_path(length, longest_matches)

    # Write start of data
    output = bytearray()
    output.append(0x10)
    output.append(length & 0xFF)
    output.append((length >> 8) & 0xFF)
    output.append((length >> 16))

    for i in range(len(path) - 2, -1, -1):
        next_idx = path[i]

        # Check flag
        if flag_counter == 8:
            flag_idx = len(output)
            output.append(0)
            flag_counter = 0
        
        size = next_idx - idx
        if size == 1:
            # Uncompressed
            output.append(input[idx])
        else:
            # Compressed
            match_idx = longest_matches[idx][0]
            offset = idx - match_idx - MIN_WINDOW_SIZE
            size -= MIN_MATCH_SIZE
            output.append((size << 4) | (offset >> 8))
            output.append(offset & 0xFF)
            output[flag_idx] |= 0x80 >> flag_counter
        
        idx = next_idx
        flag_counter += 1
    
    return bytes(output)


def _find_longest_matches(input: bytes) -> dict[int, tuple[int, int]]:
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
            longest_matches[i] = (longest_idx, longest_len)

    return longest_matches


def _find_best_path(length: int, longest_matches: dict[int, tuple[int, int]]) -> list[int]:
    # Set of nodes to explore, sorted by score
    heap = []
    heapq.heappush(heap, (0, 0))
    # Stores previous node on cheapest path
    came_from: dict[int, int] = {}
    # Cost of cheapest paths
    best_scores: dict[int, int] = {}
    best_scores[0] = 0

    while len(heap) > 0:
        # Get state with lowest score
        _, idx = heapq.heappop(heap)
        if idx == length:
            return _construct_path(came_from, idx)
        
        # Uncompressed
        score = best_scores[idx] + 9
        n = idx + 1
        prev_score = best_scores.get(n)
        if prev_score is None or score < prev_score:
            came_from[n] = idx
            best_scores[n] = score
            heapq.heappush(heap, (score, n))
        
        # Compressed
        longest = longest_matches.get(idx)
        if longest is not None:
            longest_len = longest[1]
            score += 8
            for size in range(MIN_MATCH_SIZE, longest_len + 1):
                n = idx + size
                prev_score = best_scores.get(n)
                if prev_score is None or score < prev_score:
                    came_from[n] = idx
                    best_scores[n] = score
                    heapq.heappush(heap, (score, n))

    raise Exception("Processed heap without reaching input length")


def _construct_path(came_from: dict[int, int], idx: int) -> list[int]:
    path: list[int] = [idx]
    while idx in came_from:
        idx = came_from[idx]
        path.append(idx)
    return path


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
