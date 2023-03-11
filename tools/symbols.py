from enum import Enum
from typing import Dict, Set

from constants import *
from game_info import GameInfo
from rom import ROM_OFFSET


class LabelType(Enum):
    Undef = 0
    Imm = 1
    Data = 2
    Code = 3


class Symbols(object):

    def __init__(self, info: GameInfo = None):
        self.thumb_code: Set[int] = set()
        self.globals: Dict[int, str] = {}
        self.locals: Set[int] = set()
        self.local_indexes: Dict[int, int] = {}
        if info is not None:
            for entry in info.ram:
                addr = entry.addr
                assert isinstance(addr, int)
                self.globals[addr] = entry.label
            for entry in info.code:
                addr = entry.addr
                assert isinstance(addr, int)
                self.globals[addr + ROM_OFFSET] = entry.label
                self.thumb_code.add(addr + ROM_OFFSET + 1)
            for entry in info.data:
                addr = entry.addr
                assert isinstance(addr, int)
                self.globals[addr + ROM_OFFSET] = entry.label

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
        # check for existing label
        if offset in self.globals:
            return self.globals[offset]
        # check for code
        if offset % 4 == 1 and offset in self.thumb_code:
            return self.globals[offset - 1] + "+1"
        pa = offset - ROM_OFFSET
        if pa in self.locals:
            return self.get_local(pa)
        # create label using offset
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
