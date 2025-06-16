import argparse
from enum import Enum, auto
import os
import re

import argparse_utils as apu
from constants import *
from info_file_utils import load_yaml_file
from rom import Rom


class TextFormat(Enum):

    MAGE = auto()
    DECOMP = auto()


def get_char_map(game: str, region: str) -> dict[int, str]:
    path = os.path.join(YAML_PATH, game, "char_map.yml")
    sections = load_yaml_file(path)
    char_map = {}
    for section in sections:
        if region in section["regions"]:
            char_map.update(section["chars"])
    return char_map


def get_formatted_control_char(text: str, arg_val: int, fmt: TextFormat) -> str:
    if text is None:
        return None
    if arg_val is not None:
        if fmt == TextFormat.MAGE:
            text = f"{text}={arg_val:X}"
        else:
            text = f"{text}({arg_val})"
    if fmt == TextFormat.MAGE:
        return "[" + text + "]"
    else:
        return "{" + text + "}"


def get_control_char_mf(val: int, fmt: TextFormat) -> str:
    if val < 0x8000:
        return None
    text = None
    arg_val = None
    msn = val >> 12
    if msn == 8:
        msb = val >> 8
        arg_val = val & 0xFF
        if msb == 0x80:
            text = "SPACE"
        elif msb == 0x81:
            text = "COLOR"
        elif msb == 0x82:
            text = "SPEED"
        elif msb == 0x83:
            text = "INDENT"
    elif msn == 9:
        text = "PLAY_SOUND"
        arg_val = val & 0xFFF
    elif msn == 0xA:
        text = "STOP_SOUND"
        arg_val = val & 0xFFF
    elif msn == 0xB:
        if val == 0xB001:
            text = "SAMUS_FACE"
        elif val == 0xB002:
            text = "SA-X_FACE"
        elif val == 0xB003:
            text = "GAME_START"
    elif msn == 0xC:
        # TODO: Investigate more
        return "END_CONVO"
    elif msn == 0xE:
        msb = val >> 8
        if msb == 0xE0:
            if val == 0xE000:
                text = "TARGET"
            # TODO: 0xE001
        elif msb == 0xE1:
            text = "WAIT"
            arg_val = val & 0xFF
        elif msb == 0xE2:
            if val == 0xE200:
                text = "ADAM"
            elif val == 0xE201:
                text = "SAMUS"
            elif val == 0xE202:
                text = "FEDERATION"
        elif msb == 0xE3:
            if val == 0xE300:
                text = "POPUP_OPEN"
            elif val == 0xE301:
                text = "POPUP_CLOSE"
    elif msn == 0xF:
        if val == 0xFB00:
            text = "OBJECTIVE" # TODO: Allow adding newline
        elif val == 0xFC00:
            text = "AWAIT_INPUT" # TODO: Allow adding newline
        elif val == 0xFD00:
            text = "NEW_PAGE" # TODO: Allow adding newline
        elif val == 0xFE00:
            if fmt == TextFormat.MAGE:
                return "\n"
            else:
                return "\\n"
        elif val == 0xFF00:
            text = "END"
    return get_formatted_control_char(text, arg_val, fmt)


def get_control_char_zm(val: int, fmt: TextFormat) -> str:
    if val < 0x8000:
        return None
    text = None
    arg_val = None
    msb = val >> 8
    if msb == 0x80:
        text = "SPACE"
        arg_val = val & 0xFF
    elif msb == 0x81:
        text = "COLOR"
        arg_val = val & 0xFF
    elif msb == 0x83:
        text = "INDENT"
        arg_val = val & 0xFF
    elif msb == 0xE1:
        text = "WAIT"
        arg_val = val & 0xFF
    elif msb == 0xFC:
        text = "AWAIT_INPUT" # TODO: Allow adding newline
    elif msb == 0xFD:
        text = "NEW_PAGE" # TODO: Allow adding newline
    elif msb == 0xFE:
        if fmt == TextFormat.MAGE:
            return "\n"
        else:
            return "\\n"
    elif msb == 0xFF:
        return "[END]"
    return get_formatted_control_char(text, arg_val, fmt)


def get_text(char_map: dict[int, str], rom: Rom, addr: int, fmt: TextFormat) -> str:
    assert addr % 2 == 0
    if rom.game == GAME_MF:
        get_control_char = get_control_char_mf
    elif rom.game == GAME_ZM:
        get_control_char = get_control_char_zm
    text = ""
    rom.seek(addr)
    while True:
        val = rom.read_next_16()
        if val >> 8 == 0xFF:
            return text
        ch = char_map.get(val)
        if ch is None:
            ch = get_control_char(val, fmt)
            if ch is None:
                ch = f"[\\x{val:04X}]"
        else:
            if fmt != TextFormat.MAGE:
                ch = re.sub(r"^\[(.+)\]$", r"{\1}", ch)
        text += ch


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    apu.add_arg(parser, apu.ArgType.ROM_PATH)
    apu.add_arg(parser, apu.ArgType.ADDR)

    args = parser.parse_args()
    rom = apu.get_rom(args.rom_path)
    addr = apu.get_hex(args.addr)

    region = rom.region
    if rom.game == GAME_ZM and region == REGION_BETA:
        region = REGION_U
    char_map = get_char_map(rom.game, region)
    text = get_text(char_map, rom, addr, TextFormat.DECOMP)
    print(text)
