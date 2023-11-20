from abc import ABC, abstractmethod
import argparse
import math
from typing import List

import argparse_utils as apu
from rom import Rom


def to_u16_le(num: int) -> bytes:
    return num.to_bytes(2, "little")


def to_u32_le(num: int) -> bytes:
    return num.to_bytes(4, "little")


def to_u16_be(num: int) -> bytes:
    return num.to_bytes(2, "big")


def to_u32_be(num: int) -> bytes:
    return num.to_bytes(4, "big")


def to_float80(num: float):
    sign = 0 if num >= 0 else 1
    num = abs(num)
    exp = int(math.log2(num))
    frac = int((num / 2**exp) * 2**63)
    exp += 0x3FFF
    bits = (sign << 79) | (exp << 64) | frac
    return bits.to_bytes(10, "big")


class WavChunk(ABC):

    def get_bytes(self) -> bytes:
        id_bytes = self.get_id().encode("ascii")
        data_bytes = self.get_data()
        size = len(data_bytes)
        if size % 2 != 0:
            data_bytes += b"\0"
            size += 1
        size_bytes = to_u32_le(size)
        return id_bytes + size_bytes + data_bytes

    @abstractmethod
    def get_id(self) -> str:
        pass

    @abstractmethod
    def get_data(self) -> bytes:
        pass


class WavRiffChunk(WavChunk):

    def __init__(self, chunks: List[WavChunk]):
        self.chunks = chunks

    def get_id(self) -> str:
        return "RIFF"
    
    def get_data(self) -> bytes:
        type_bytes = "WAVE".encode("ascii")
        chunks_bytes = b"".join(c.get_bytes() for c in self.chunks)
        return type_bytes + chunks_bytes


class WavFmtChunk(WavChunk):

    def __init__(self,
        num_channels: int,
        sample_size: int,
        sample_rate: int 
    ):
        """
        num_channels: 1 = mono, 2 = stereo
        sample_size: bits per sample
        sample_rate: sample blocks per second
        """
        self.num_channels = num_channels
        self.sample_size = sample_size
        self.sample_rate = sample_rate

    def get_id(self) -> str:
        return "fmt "
    
    def get_data(self) -> bytes:
        block_align = self.num_channels * self.sample_size // 8
        byte_rate = self.sample_rate * block_align
        return b"".join([
            to_u16_le(1),
            to_u16_le(self.num_channels),
            to_u32_le(self.sample_rate),
            to_u32_le(byte_rate),
            to_u16_le(block_align),
            to_u16_le(self.sample_size)
        ])


class WavDataChunk(WavChunk):

    def __init__(self,
        sound_data: bytes
    ):
        """
        sound_data: sound sample blocks
        """
        self.sound_data = sound_data

    def get_id(self) -> str:
        return "data"
    
    def get_data(self) -> bytes:
        return bytes([(b + 0x80) & 0xFF for b in self.sound_data])


class AiffChunk(ABC):

    def get_bytes(self) -> bytes:
        id_bytes = self.get_id().encode("ascii")
        data_bytes = self.get_data()
        size = len(data_bytes)
        if size % 2 != 0:
            data_bytes += b"\0"
            size += 1
        size_bytes = to_u32_be(size)
        return id_bytes + size_bytes + data_bytes

    @abstractmethod
    def get_id(self) -> str:
        pass

    @abstractmethod
    def get_data(self) -> bytes:
        pass


class AiffFormChunk(AiffChunk):

    def __init__(self, chunks: List[AiffChunk]):
        self.chunks = chunks

    def get_id(self) -> str:
        return "FORM"
    
    def get_data(self) -> bytes:
        type_bytes = "AIFF".encode("ascii")
        chunks_bytes = b"".join(c.get_bytes() for c in self.chunks)
        return type_bytes + chunks_bytes


class AiffCommonChunk(AiffChunk):

    def __init__(self,
        num_channels: int,
        sample_size: int,
        sample_rate: float,
        num_sample_frames: int
    ):
        """
        num_channels: 1 = mono, 2 = stereo
        sample_size: bits per sample point
        sample_rate: sample frames per second
        num_sample_frames: number of sample frames in sound data chunk
        """
        self.num_channels = num_channels
        self.sample_size = sample_size
        self.sample_rate = sample_rate
        self.num_sample_frames = num_sample_frames

    def get_id(self) -> str:
        return "COMM"
    
    def get_data(self) -> bytes:
        return b"".join([
            to_u16_be(self.num_channels),
            to_u32_be(self.num_sample_frames),
            to_u16_be(self.sample_size),
            to_float80(self.sample_rate)
        ])


class AiffSoundChunk(AiffChunk):

    def __init__(self,
        sound_data: bytes,
        offset: int = 0,
        block_size: int = 0,
    ):
        """
        sound_data: sound sample frames
        offset: offset of first sample frame in sound_data, usually 0
        block_size: size of blocks sound data is aligned to, usually 0
        """
        self.offset = offset
        self.block_size = block_size
        self.sound_data = sound_data

    def get_id(self) -> str:
        return "SSND"
    
    def get_data(self) -> bytes:
        return b"".join([
            to_u32_be(self.offset),
            to_u32_be(self.block_size),
            self.sound_data
        ])


def dump_pcm(rom: Rom, addr: int, format: str, path: str) -> None:
    # get data from rom
    pitch = rom.read_32(addr + 4)
    sample_rate = pitch / 1024
    size = rom.read_32(addr + 0xC)
    sound_data = rom.read_bytes(addr + 0x10, size)
    # create wav or aiff file
    file_bytes = None
    if format == "wav":
        fmt_chunk = WavFmtChunk(1, 8, int(sample_rate))
        data_chunk = WavDataChunk(sound_data)
        riff_chunk = WavRiffChunk([fmt_chunk, data_chunk])
        file_bytes = riff_chunk.get_bytes()
    elif format == "aiff":
        common_chunk = AiffCommonChunk(1, 8, sample_rate, size)
        sound_chunk = AiffSoundChunk(sound_data)
        form_chunk = AiffFormChunk([common_chunk, sound_chunk])
        file_bytes = form_chunk.get_bytes()
    else:
        raise ValueError(format)
    with open(path, "wb") as f:
        f.write(file_bytes)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    apu.add_arg(parser, apu.ArgType.ROM_PATH)
    apu.add_arg(parser, apu.ArgType.ADDR)
    parser.add_argument("format", type=str, choices=("wav", "aiff"))
    parser.add_argument("path", type=str)

    args = parser.parse_args()
    rom = apu.get_rom(args.rom_path)
    addr = apu.get_hex(args.addr)
    dump_pcm(rom, addr, args.format, args.path)
