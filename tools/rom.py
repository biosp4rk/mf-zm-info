from typing import Dict, Optional, Union

from constants import *


BytesLike = Union[bytes, bytearray]

SIZE_8MB = 0x800000
SIZE_16MB = SIZE_8MB * 2
SIZE_32MB = SIZE_16MB * 2

ROM_OFFSET = 0x8000000
ROM_END = ROM_OFFSET + SIZE_32MB


class Rom(object):
    def __init__(self, path: str):
        # read file
        with open(path, "rb") as f:
            self.data = bytearray(f.read())
        # check length
        if len(self.data) != SIZE_8MB:
            raise ValueError("ROM should be 8MB")
        # check title and code
        title = self.read_ascii(0xA0, 0x10)
        if title == "METROID4USA\0AMTE":
            self.game = GAME_MF
            self.region = REGION_U
        elif title == "METROID4EUR\0AMTP":
            self.game = GAME_MF
            self.region = REGION_E
        elif title == "METROID4JPN\0AMTJ":
            self.game = GAME_MF
            self.region = REGION_J
        elif title == "METFUSIONCHNAMTC":
            self.game = GAME_MF
            self.region = REGION_C
        elif title == "ZEROMISSIONEBMXE":
            self.game = GAME_ZM
            self.region = REGION_U
        elif title == "ZEROMISSIONPBMXP":
            self.game = GAME_ZM
            self.region = REGION_E
        elif title == "ZEROMISSIONJBMXJ":
            self.game = GAME_ZM
            self.region = REGION_J
        elif title == "ZEROMISSIONCBMXC":
            self.game = GAME_ZM
            self.region = REGION_C
        else:
            raise ValueError("Not a valid GBA Metroid ROM")
        self.pos = None

    def read_8(self, addr: int) -> int:
        return self.data[addr]

    def read_16(self, addr: int) -> int:
        return self.data[addr] | (self.data[addr + 1] << 8)

    def read_32(self, addr: int) -> int:
        return (
            self.data[addr] |
            (self.data[addr + 1] << 8) |
            (self.data[addr + 2] << 16) |
            (self.data[addr + 3] << 24)
        )

    def read_ptr(self, addr: int) -> int:
        val = self.read_32(addr)
        if val < ROM_OFFSET:
            raise ValueError(f"Invalid pointer {val:X} at {addr:X}")
        return val - ROM_OFFSET

    def read_bytes(self, addr: int, size: int) -> bytearray:
        end = addr + size
        return self.data[addr:end]

    def read_ascii(self, addr: int, size: int) -> str:
        return self.read_bytes(addr, size).decode("ascii")

    def write_8(self, addr: int, val: int) -> None:
        self.data[addr] = val

    def write_16(self, addr: int, val: int) -> None:
        val &= 0xFFFF
        self.data[addr] = val & 0xFF
        self.data[addr + 1] = val >> 8

    def write_32(self, addr: int, val: int) -> None:
        val &= 0xFFFFFFFF
        self.data[addr] = val & 0xFF
        self.data[addr + 1] = (val >> 8) & 0xFF
        self.data[addr + 2] = (val >> 16) & 0xFF
        self.data[addr + 3] = val >> 24

    def write_ptr(self, addr: int, val: int) -> None:
        assert val < ROM_OFFSET, f"Pointer should be less than {ROM_OFFSET:X} but is {val:X}"
        self.write_32(addr, val + ROM_OFFSET)
        
    def write_bytes(
        self,
        dst_addr: int,
        vals: BytesLike,
        src_addr: int = 0,
        size: Optional[int] = None
    ) -> None:
        if size is None:
            size = len(vals) - src_addr
        dst_end = dst_addr + size
        src_end = src_addr + size
        self.data[dst_addr:dst_end] = vals[src_addr:src_end]

    def seek(self, addr: int) -> None:
        assert 0 <= addr < len(self.data)
        self.pos = addr

    def tell(self) -> int:
        assert self.pos is not None
        return self.pos

    def read_next_8(self) -> int:
        val = self.read_8(self.pos)
        self.pos += 1
        return val
    
    def read_next_16(self) -> int:
        val = self.read_16(self.pos)
        self.pos += 2
        return val

    def read_next_ptr(self) -> int:
        val = self.read_ptr(self.pos)
        self.pos += 4
        return val

    def code_start(self, virt: bool = False) -> int:
        addr = None
        if self.game == GAME_MF:
            addr = 0x230
            # C also has code starting at 0x7FD354
        elif self.game == GAME_ZM:
            addr = 0x23C
        if virt:
            addr += ROM_OFFSET
        return addr

    def code_end(self, virt: bool = False) -> int:
        addr = None
        if self.game == GAME_MF:
            if self.region == REGION_U:
                addr = 0xA4FA4
            elif self.region == REGION_E:
                addr = 0xA5600
            elif self.region == REGION_J:
                addr = 0xA7290
            elif self.region == REGION_C:
                addr = 0xA72D4
                # C also has code ending at 0x7FD6E8
        elif self.game == GAME_ZM:
            if self.region == REGION_U:
                addr = 0x8C71C
            elif self.region == REGION_E:
                addr = 0x8D3A8
            elif self.region == REGION_J:
                addr = 0x8C778
            elif self.region == REGION_C:
                addr = 0x90294
        if virt:
            addr += ROM_OFFSET
        return addr

    def data_start(self, virt: bool = False) -> int:
        return self.code_end(virt)

    def data_end(self, virt: bool = False) -> int:
        addr = None
        if self.game == GAME_MF:
            if self.region == REGION_U:
                addr = 0x79ECC8
            elif self.region == REGION_E:
                addr = 0x79F524
            elif self.region == REGION_J:
                addr = 0x7F145C
            elif self.region == REGION_C:
                addr = 0x77ECC8
                # C also has data ending at 0x8000000
        elif self.game == GAME_ZM:
            if self.region == REGION_U:
                addr = 0x760D38
            elif self.region == REGION_E:
                addr = 0x775414
            elif self.region == REGION_J:
                addr = 0x760E48
            elif self.region == REGION_C:
                addr = 0x79FF38
        if virt:
            addr += ROM_OFFSET
        return addr

    def arm_functions(self) -> Dict[int, int]:
        if self.game == GAME_MF:
            if self.region == REGION_U:
                return {
                    0x3D78: 0x3E0C,
                    0x3E1C: 0x3EBC,
                    0x3ECC: 0x4514,
                    0x4518: 0x4530,
                    0x4534: 0x45A8
                }
            elif self.region == REGION_E:
                return {
                    0x3D78: 0x3E0C,
                    0x3E1C: 0x3EBC,
                    0x3ECC: 0x4514,
                    0x4518: 0x4530,
                    0x4534: 0x45A8
                }
            elif self.region == REGION_J:
                return {
                    0x3DDC: 0x3E70,
                    0x3E80: 0x3F20,
                    0x3F30: 0x4578,
                    0x457C: 0x4594,
                    0x4598: 0x460C
                }
            elif self.region == REGION_C:
                return {
                    0x3DDC: 0x3E70,
                    0x3E80: 0x3F20,
                    0x3F30: 0x4578,
                    0x457C: 0x4594,
                    0x4598: 0x460C
                }
        elif self.game == GAME_ZM:
            if self.region == REGION_U:
                return {
                    0x4320: 0x43B4,
                    0x43C4: 0x4464,
                    0x4474: 0x4ABC,
                    0x4AC0: 0x4AD8,
                    0x4ADC: 0x4B50
                }
            elif self.region == REGION_E:
                return {
                    0x4374: 0x4408,
                    0x4418: 0x44B8,
                    0x44C8: 0x4B10,
                    0x4B14: 0x4B2C,
                    0x4B30: 0x4BA4
                }
            elif self.region == REGION_J:
                return {
                    0x4320: 0x43B4,
                    0x43C4: 0x4464,
                    0x4474: 0x4ABC,
                    0x4AC0: 0x4AD8,
                    0x4ADC: 0x4B50
                }
            elif self.region == REGION_C:
                return {
                    0x6CD4: 0x6D68,
                    0x6D78: 0x6E18,
                    0x6E28: 0x7470,
                    0x7474: 0x748C,
                    0x7490: 0x7504
                }

    def find_bytes(self, pat: BytesLike, start: int = 0) -> int:
        return self.data.find(pat, start)
