import argparse
from collections import defaultdict
from typing import Dict, List
import os

from constants import *
from info_entry import DataEntry
from game_info import GameInfo
from rom import Rom
from yaml_utils import yaml_obj_to_str


def struct_list_var_addrs(
    info: GameInfo,
    data_label: str,
    var_label: str
) -> List[int]:
    """
    Given a data label for a list of structs and a label for a field on
    the struct, returns the address of the field for each entry.
    """
    # get data entry info
    data = info.get_data(data_label)
    data_addr = data.addr
    data_count = data.get_count()
    # get struct info
    struct = info.get_struct(data.struct_name)
    size = struct.size
    var_off = struct.get_var(var_label).offset
    # compute addresses
    addrs = []
    for i in range(data_count):
        off = i * size + var_off
        addr = {r: a + off for r, a in data_addr.items()}
        addrs.append(addr)
    return addrs


def dump_instrument_defs(roms: Dict[str, Rom]):
    first = next(iter(roms.values()))
    info = GameInfo(first.game)
    addrs = struct_list_var_addrs(info, "SoundDataEntries", "SoundHeaderPtr")
    # group entries by address
    addr_dict = defaultdict(list)
    for i, addr in enumerate(addrs):
        # get song header addresses
        addr = {r: roms[r].read_ptr(a) for r, a in addr.items()}
        # get instrument def addresses
        addr = {r: roms[r].read_ptr(a + 4) for r, a in addr.items()}
        key = tuple(addr[r] for r in REGIONS)
        addr_dict[key].append(i)
    # loop through entries
    data_entries = []
    for key, idxs in addr_dict.items():
        addr = {REGIONS[i]: a for i, a in enumerate(key)}
        idxs_desc = ", ".join(f"{i:X}" for i in idxs)
        idxs_label = "_".join(f"{i:03X}" for i in idxs)
        de = DataEntry(
            f"Sound {idxs_desc} instrument definition",
            f"InstrumentDef_Sound_{idxs_label}",
            "InstrumentDef", None, addr
        )
        data_entries.append(de)
    # sort by address and print
    data_entries.sort(key=lambda de: de.addr[REGION_U])
    for de in data_entries:
        s = yaml_obj_to_str(DataEntry.to_yaml_obj(de))
        print(s, end="")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("roms_dir", type=str,
        help="Path of directory containing ROMs")
    parser.add_argument("game", type=str, choices=(GAME_MF, GAME_ZM),
        help="ROM name prefix")
    parser.add_argument("data", type=str,
        help="Name of data to dump")

    args = parser.parse_args()
    files = os.listdir(args.roms_dir)
    files = [f for f in files if f.startswith(args.game) and f.endswith(".gba")]
    paths = [os.path.join(args.roms_dir, f) for f in files]
    roms = [Rom(p) for p in paths]
    roms = {r.region: r for r in roms}

    if args.data == "instrument_defs":
        dump_instrument_defs(roms)
    else:
        parser.print_help()
