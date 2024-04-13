import argparse
import os
from typing import Dict

import argparse_utils as apu
from constants import *
from rom import Rom
from info_file_utils import load_yaml_file


def get_char_map(game: str, region: str) -> Dict[int, str]:
    path = os.path.join(YAML_PATH, game, "char_map.yml")
    sections = load_yaml_file(path)
    char_map = {}
    for section in sections:
        if region in section["regions"]:
            char_map.update(section["chars"])
    return char_map


def get_control_char_mf(val: int) -> str:
    if val < 0x8000:
        return None
    msn = val >> 12
    if msn == 8:
        msb = val >> 8
        lsb = val & 0xFF
        if msb == 0x80:
            return f"[SPACE={lsb:X}]"
        elif msb == 0x81:
            return f"[COLOR={lsb:X}]"
        elif msb == 0x82:
            return f"[SPEED={lsb:X}]"
        elif msb == 0x83:
            return f"[INDENT={lsb:X}]"
    elif msn == 9:
        return f"[PLAY_SOUND={val & 0xFFF:X}]"
    elif msn == 0xA:
        return f"[STOP_SOUND={val & 0xFFF:X}]"
    elif msn == 0xB:
        if val == 0xB001:
            return "[SAMUS_FACE]"
        elif val == 0xB002:
            return "[SA-X_FACE]"
        elif val == 0xB003:
            return "[GAME_START]"
    elif msn == 0xC:
        # TODO: investigate more
        return "[END_CONVO]"
    elif msn == 0xE:
        msb = val >> 8
        if msb == 0xE0:
            if val == 0xE000:
                return "[TARGET]"
            # TODO: 0xE001
        elif msb == 0xE1:
            return f"[WAIT={val & 0xFF:X}]"
        elif msb == 0xE2:
            if val == 0xE200:
                return "[ADAM]"
            elif val == 0xE201:
                return "[SAMUS]"
            elif val == 0xE202:
                return "[FEDERATION]"
        elif msb == 0xE3:
            if val == 0xE300:
                return "[POPUP_OPEN]"
            elif val == 0xE301:
                return "[POPUP_CLOSE]"
    elif msn == 0xF:
        if val == 0xFB00:
            return "[OBJECTIVE]\n"
        elif val == 0xFC00:
            return "[AWAIT_INPUT]\n"
        elif val == 0xFD00:
            return "[NEW_PAGE]\n"
        elif val == 0xFE00:
            return "\n"
        elif val == 0xFF00:
            return "[END]"
    return None


def get_control_char_zm(val: int) -> str:
    if val < 0x8000:
        return None
    msb = val >> 8
    if msb == 0x80:
        return f"[SPACE={val & 0xFF:X}]"
    elif msb == 0x81:
        return f"[COLOR={val & 0xFF:X}]"
    elif msb == 0x83:
        return f"[INDENT={val & 0xFF:X}]"
    elif msb == 0xE1:
        return f"[WAIT={val & 0xFF:X}]"
    elif msb == 0xFC:
        return "[AWAIT_INPUT]\n"
    elif msb == 0xFD:
        return "[NEW_PAGE]\n"
    elif msb == 0xFE:
        return "\n"
    elif msb == 0xFF:
        return "[END]"
    return None


def get_text(char_map: Dict[int, str], rom: Rom, addr: int) -> str:
    assert addr % 2 == 0
    if rom.game == GAME_MF:
        get_control_char = get_control_char_mf
    elif rom.game == GAME_ZM:
        get_control_char = get_control_char_zm
    text = ""
    rom.seek(addr)
    while True:
        val = rom.read_next_16(addr)
        if val >> 8 == 0xFF:
            return text
        ch = char_map.get(val)
        if ch is None:
            ch = get_control_char(val)
            if ch is None:
                ch = f"[\\x{val:04X}]"
        text += ch


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    apu.add_arg(parser, apu.ArgType.ROM_PATH)
    apu.add_arg(parser, apu.ArgType.ADDR)

    args = parser.parse_args()
    rom = apu.get_rom(args.rom_path)
    addr = apu.get_hex(args.addr)

    char_map = get_char_map(rom.game, rom.region)
    text = get_text(char_map, rom, addr)
    print(text)
