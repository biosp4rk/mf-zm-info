import os
import re
from typing import Any, Dict, List, Union
import yaml
from constants import *


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
                key=lambda e: region_int_to_int(r, e["addr"]))
            if r == REGIONS[0]:
                combined = entries
                continue
            i = len(entries) - 1
            j = len(combined) - 1
            while i > 0:
                entry = entries[i]
                addr = region_int_to_int(r, entry["addr"])
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


def region_int_to_int(region: str, entry: RegionInt) -> int:
    if isinstance(entry, int):
        return entry
    return entry.get(region)


def region_int_to_dict(regions: List[str], entry: RegionInt) -> Dict[str, int]:
    if isinstance(entry, dict):
        return entry
    return {r: entry for r in regions}


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
            fields = FIELDS[k]
            for i, field in enumerate(fields):
                if field in entry:
                    v = entry.pop(field)
                    # add index to keep fields in order
                    entry[f"{i:03}~{field}"] = v
                    stack.append((v, field))
        elif isinstance(entry, list):
            stack += [(e, k) for e in entry]

    # get output
    output = yaml.dump(data)
    # remove index from fields
    output = re.sub(r"\d+~", "", output)
    if isinstance(data, list):
        # add extra line breaks for lists
        output = re.sub(r"^- ", "-\n  ", output, flags=re.MULTILINE)
    with open(path, "w") as f:
        f.write(output)


def get_spec_size(spec: str, structs: Dict[str, Any]) -> int:
    if spec in PRIMITIVES:
        return PRIMITIVES[spec]
    if spec in structs:
        return structs[spec]["size"]
    raise ValueError(f"Invalid type specifier {spec}")


def get_entry_size(
    entry: Dict[str, Any], structs: Dict[str, Any]
) -> Dict[str, int]:
    # get regions this entry applies to
    regions = REGIONS
    addr = entry["addr"]
    if isinstance(addr, dict):
        regions = tuple(addr.keys())
    # return size field if present
    if "size" in entry:
        return region_int_to_dict(regions, entry["size"])
    # parse type
    parts = entry["type"].split()
    spec = parts[0]
    size = get_spec_size(spec, structs)
    if len(parts) == 2:
        decl = parts[1]
        # get inner-most part of declaration
        i = decl.rfind("(")
        if i != -1:
            j = decl.index(")")
            decl = decl[i+1:j]
        # check for pointer
        if decl.startswith("*"):
            size = 4
            decl = decl.lstrip("*")
        # check for array
        dims = [int(m) for m in re.findall(r"\d+", decl)]
        for dim in dims:
            size *= dim
    return {r: size for r in regions}


def get_new_type(entry):
    parts = entry["type"].split(".")
    spec = "void"
    is_ptr = False
    count = entry.get("count", 1)
    tags = []
    for part in parts:
        if part in PRIMITIVES:
            spec = part
        elif part == "flags8":
            spec = "u8"
            tags.append("flags")
        elif part == "flags16":
            spec = "u16"
            tags.append("flags")
        elif part == "ptr":
            is_ptr = True
        elif part == "ascii":
            spec = "s8"
            tags.append("ascii")
        elif part == "char":
            spec = "u16"
            tags.append("text")
        elif part == "lz":
            tags.append("lz")
        elif part == "gfx":
            spec = "u8"
            tags.append("gfx")
        elif part == "tilemap":
            spec = "u16"
            tags.append("tilemap")
        elif part == "palette":
            spec = "u16"
            tags.append("palette")
        elif part == "thumb":
            spec = "void"
            tags.append("thumb")
        elif part == "arm":
            spec = "void"
            tags.append("arm")
        else:
            spec = part
    decl = ""
    if is_ptr:
        decl += "*"
    if count > 1:
        decl += f"[0x{count:X}]"
    if decl:
        spec += " " + decl
    return spec, tags

# TODO:
# fix gfx and palette counts in all files
# convert sizes to counts for vars
