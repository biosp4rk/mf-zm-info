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

    def get_local(self, addr: int, prefixed: bool) -> str:
        idx = self.local_indexes[addr]
        prefix = "@@" if prefixed else ""
        return f"{prefix}_{idx:03X}"

    def get_label(self, addr: int, prefixed: bool, type: LabelType = LabelType.Undef) -> str:
        # Check for existing label
        if addr in self.globals:
            return self.globals[addr]
        # Check for code
        if addr % 4 == 1 and addr in self.thumb_code:
            return self.globals[addr - 1] + "+1"
        pa = addr - ROM_OFFSET
        if pa in self.locals:
            return self.get_local(pa, prefixed)
        # Create label using addr
        label = f"{addr:X}"
        if type == LabelType.Imm:
            label = "0x" + label
        elif type == LabelType.Data:
            label = "unk_" + label
        elif type == LabelType.Code:
            label = "sub_" + label
        return label

    def reset_locals(self):
        self.locals = set()
        self.local_indexes = {}
