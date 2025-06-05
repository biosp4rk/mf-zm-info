from enum import Enum, auto

from constants import *
from game_info import GameInfo
from rom import ROM_OFFSET


class LabelType(Enum):

    Undef = auto()
    Imm = auto()
    Data = auto()
    Code = auto()


class Symbols(object):

    def __init__(self, info: GameInfo = None):
        self.thumb_code: set[int] = set()
        self.globals: dict[int, str] = {}
        self.locals: set[int] = set()
        self.local_indexes: dict[int, int] = {}
        if info is not None:
            for entry in info.ram:
                addr = entry.addr
                assert isinstance(addr, int)
                self.globals[addr] = entry.name
            for entry in info.code:
                addr = entry.addr
                assert isinstance(addr, int)
                self.globals[addr + ROM_OFFSET] = entry.name
                self.thumb_code.add(addr + ROM_OFFSET + 1)
            for entry in info.data:
                addr = entry.addr
                assert isinstance(addr, int)
                self.globals[addr + ROM_OFFSET] = entry.name

    def add_global(self, addr: int, label: str):
        self.globals[addr] = label

    def add_local(self, addr: int):
        self.locals.add(addr)

    def finalize_locals(self):
        idx = 0
        for addr in sorted(self.locals):
            self.local_indexes[addr] = idx
            idx += 1

    def reset_locals(self):
        self.locals = set()
        self.local_indexes = {}
