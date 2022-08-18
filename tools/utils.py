import os
import re
from typing import Any, Dict, List, Union
import yaml
from constants import *


TYPE_SIZES = {
    "u8": 1,
    "s8": 1,
    "flags8": 1,
    "bool": 1,
    "u16": 2,
    "s16": 2,
    "flags16": 2,
    "char": 2,
    "u32": 4,
    "s32": 4,
    "ptr": 4,
    "palette": 32
}
InfoFile = Union[Dict, List]


def hexint_presenter(dumper, data):
    return dumper.represent_int(f"0x{data:X}")


yaml.add_representer(int, hexint_presenter)


def read_yaml(path: str) -> InfoFile:
    with open(path) as f:
        return yaml.full_load(f)


def read_yamls(game: str, map_type: str) -> InfoFile:
    dir_path = os.path.join(YAML_PATH, game, map_type)
    file_path = dir_path + YAML_EXT
    data_dict = None
    if os.path.isfile(file_path):
        data_dict = {file_path: read_yaml(file_path)}
    elif os.path.isdir(dir_path):
        files = [f for f in os.listdir(dir_path) if f.endswith(YAML_EXT)]
        files = [os.path.join(dir_path, f) for f in files]
        data_dict = {f: read_yaml(f) for f in files}
    else:
        raise ValueError("No file or directory found")
    return combine_yamls(list(data_dict.values()))


def combine_yamls(data_list: List[InfoFile]) -> InfoFile:
    combined = data_list[0]
    for data in data_list[1:]:
        if isinstance(combined, list) and isinstance(data, list):
            combined += data
        elif isinstance(combined, dict) and isinstance(data, dict):
            combined.update(data)
        else:
            raise ValueError("Type mismatch")
    if isinstance(combined, list):
        # get entries by region
        entry_dict = {r: [] for r in REGIONS}
        for entry in combined:
            addr = entry["addr"]
            if isinstance(addr, int):
                reg = REGIONS[0]
            else:
                reg = next(r for r in REGIONS if r in addr)
            entry_dict[reg].append(entry)
        # sort by U, then by E, etc
        for r in REGIONS:
            entries = sorted(entry_dict[r],
                key=lambda e: get_versioned_int(r, e["addr"]))
            if r == REGIONS[0]:
                combined = entries
                continue
            i = len(entries) - 1
            j = len(combined) - 1
            while i > 0:
                entry = entries[i]
                addr = get_versioned_int(r, entry["addr"])
                while j > 0:
                    cmp_addr = combined[j]["addr"]
                    if isinstance(cmp_addr, dict):
                        cmp_addr = cmp_addr.get(r, 2e32)
                    if cmp_addr < addr:
                        break
                    j -= 1
                combined.insert(j + 1, entry)
                i -= 1
    return combined


def get_versioned_int(region: str, entry: VersionedInt) -> int:
    if isinstance(entry, int):
        return entry
    return entry.get(region)


def compare_addrs(entry1, entry2) -> int:
    addr1 = entry1["addr"]
    addr2 = entry2["addr"]
    if isinstance(addr1, dict):
        for region in REGIONS:
            if region in addr1 and region in addr2:
                addr1 = addr1[region]
                addr2 = addr2[region]
                break
        if isinstance(addr1, dict):
            return 0
    return addr1 - addr2


def ints_to_strs(data: InfoFile) -> None:
    stack = [data]
    while len(stack) > 0:
        entry = stack.pop()
        if isinstance(entry, list):
            stack += entry
        elif isinstance(entry, dict):
            for k, v in entry.items():
                if isinstance(v, int):
                    entry[k] = f"{v:X}"
                elif isinstance(v, list):
                    stack += v
                else:
                    stack.append(v)


ABBREV = {
    "Alternate": "Alt",
    "Background": "BG",
    "Current": "Curr",
    "Graphics": "Gfx",
    "Initialize": "Init",
    "Navigation": "Nav",
    "Number": "Num",
    "Previous": "Prev",
    "Pointer": "Ptr"
}

def desc_to_label(desc: str) -> str:
    words = re.split(r"\W+", desc)
    words = [word.capitalize() for word in words]
    words = [ABBREV.get(word, word) for word in words]
    return "".join(words)

def write_yaml(path: str, data: InfoFile, map_type: str) -> None:
    # create stack of entries
    if isinstance(data, dict):
        stack = [(v, map_type) for v in data.values()]
    elif isinstance(data, list):
        stack = [(d, map_type) for d in data]
    else:
        raise ValueError("Bad format")
    # check for required fields
    while len(stack) > 0:
        entry, k = stack.pop()
        if isinstance(entry, dict):
            #
            if "desc" in entry:
                desc = entry.pop("desc")
                if "notes" not in entry:
                    entry["notes"] = desc
                if "label" not in entry:
                    if desc == "?":
                        if "offset" not in entry:
                            print(entry)
                            input()
                        lab = "?"
                    else:
                        lab = desc_to_label(desc)
                    print(lab)
            #
            fields = FIELDS[k]
            for i, field in enumerate(fields):
                if field in entry:
                    v = entry.pop(field)
                    # add index to keep fields in order
                    entry[f"{i:03}~{field}"] = v
                    stack.append((v, field))
        elif isinstance(entry, list):
            stack += [(e, k) for e in entry]

    return

    # get output
    output = yaml.dump(data)
    # remove index from fields
    output = re.sub(r"\d+~", "", output)
    if isinstance(data, list):
        # add extra line breaks for lists
        output = re.sub(r"^- ", "-\n  ", output, flags=re.MULTILINE)
    # try parsing output to make sure it's valid
    yaml.full_load(output)
    with open(path, "w") as f:
        f.write(output)


def get_type_size(entry: Dict[str, Any], structs: Dict[str, Any]) -> int:
    t = entry["type"].split(".")[0]
    if t in TYPE_SIZES:
        return TYPE_SIZES[t]
    if t in structs:
        return structs[t]["size"]
    raise ValueError(f"Invalid type {t}")


def get_entry_size(
    entry: Dict[str, Any], structs: Dict[str, Any]
) -> Dict[str, int]:
    # get regions this entry applies to
    addr = entry["addr"]
    if isinstance(addr, dict):
        regions = addr.keys()
    else:
        regions = REGIONS
    # return size field if present
    if "size" in entry:
        size = entry["size"]
        if isinstance(size, int):
            size = {r: size for r in regions}
        return size
    # can't get size if type isn't known
    if "type" not in entry:
        return {r: 0 for r in regions}
    # multiply type size by count
    ts = get_type_size(entry, structs)
    if "count" in entry:
        count = entry["count"]
        if isinstance(count, int):
            count = {r: count for r in regions}
    else:
        count = {r: 1 for r in regions}
    for r in count:
        count[r] *= ts
    return count
