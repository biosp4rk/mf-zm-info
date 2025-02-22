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

    def add_global(self, offset: int, label: str):
        self.globals[offset] = label

    def add_local(self, offset: int):
        self.locals.add(offset)

    def finalize_locals(self):
        idx = 0
        for addr in sorted(self.locals):
            self.local_indexes[addr] = idx
            idx += 1

    def get_local(self, offset: int) -> str:
        idx = self.local_indexes[offset]
        return f"@@_{idx:03X}"

    def get_label(self, offset: int, type: LabelType = LabelType.Undef) -> str:
        # Check for existing label
        if offset in self.globals:
            return self.globals[offset]
        # Check for code
        if offset % 4 == 1 and offset in self.thumb_code:
            return self.globals[offset - 1] + "+1"
        pa = offset - ROM_OFFSET
        if pa in self.locals:
            return self.get_local(pa)
        # Create label using offset
        label = f"{offset:X}"
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
