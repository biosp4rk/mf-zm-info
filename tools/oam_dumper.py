import argparse

import argparse_utils as apu
from rom import Rom


D16 = ".dh"
D32 = ".dw"
INDENT = " " * 4


def dump(rom: Rom, addr: int) -> None:
    data_start = rom.data_start(True)
    data_end = rom.data_end(True)
    lines1 = [".align 2", ""]
    lines2 = [".align", ""]
    oam_num = 0
    frame_num = 0

    while True:
        # for each pose
        offset = rom.read_32(addr)
        if offset < data_start or offset >= data_end:
            break
  
        lines2.append(f"Oam_{oam_num}:")
        lines2.append(f"{INDENT}; {addr:X}")

        while True:
            # for each frame
            offset = rom.read_32(addr)
            if offset == 0:
                addr += 8
                break
                
            offset = rom.read_ptr(addr)
            addr += 4
            duration = rom.read_32(addr)
            addr += 4

            branch_name = f"Oam_{oam_num}_Frame_{frame_num}"
            lines1.append(branch_name + ":")
            lines2.append(f"{INDENT}{D32} {branch_name}")
            lines2.append(f"{INDENT}{D32} {duration}")

            rom.seek(offset)
            num_parts = rom.read_next_16()
            lines1.append(f"{INDENT}{D16} {num_parts}")

            for _ in range(num_parts):
                # for each piece
                attr1 = rom.read_next_16()
                attr2 = rom.read_next_16()
                attr3 = rom.read_next_16()

                a1 = get_attr_str(attr1)
                a2 = get_attr_str(attr2)
                a3 = get_attr_str(attr3)
                lines1.append(f"{INDENT}{D16} {a1},{a2},{a3}")

            frame_num += 1

        lines1.append("")
        lines2.append(f"{INDENT}{D32} 0,0")
        lines2.append("")
        oam_num += 1

    # output
    print("\n".join(lines1) + "\n" + "\n".join(lines2))


def get_attr_str(attr: int) -> str:
    return f"0x{attr:04X}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    apu.add_arg(parser, apu.ArgType.ROM_PATH)
    apu.add_arg(parser, apu.ArgType.ADDR)

    args = parser.parse_args()
    rom = apu.get_rom(args.rom_path)
    addr = apu.get_hex(args.addr)
    dump(rom, addr)
