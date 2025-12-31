# Overview:
# - Find defs in .h files (typedefs, vars, funcs, enums, structs, unions)
#   - names, types, fields, (partial) sizes, locations
# - Prefer locations from .c files (for funcs and rom data)
# - Extract docstrings above each location, if any (prefer .c files)
# - Compute sizes of structs and vars, using typedefs and evaluating statements
# - Parse elf file to get addresses and sizes
# - Load existing info entries
# - Update entry fields (except for cat, comp, enum, and refs)

# Elf file command:
# readelf <game>.elf -s -W > <output>

import argparse
from collections import defaultdict
import os
from pathlib import Path
import re
import sys

from pycparser import c_ast, parse_file, plyparser

from constants import *
import decomp.elf_parser as ep
from info.asset_type import BUILT_IN_TYPES, BUILT_IN_SIZES
from info.game_info import GameInfo, InfoSource
from info.info_entry import *
import info.info_file_utils as ifu


DOC_STR_BRIEF = re.compile(r"@brief\s+(.+)")
DOC_STR_PARAM = re.compile(r"@param\s+(\w+)\s+(.+)")
DOC_STR_RETURN = re.compile(r"@return\s+(.+)")
DOC_STR_LINE = re.compile(r"\*\s+(.+)")
DOC_STR_ADDR_SIZE = re.compile(r"\w+\s*\|\s*\w+\s*\|\s*(.+)")


def get_files_with_ext(dir: str, ext: str, exclude: str = None) -> list[str]:
    """Recursively search for files with the given extension."""
    paths = []
    is_top = True
    for dirpath, dirnames, filenames in os.walk(dir):
        if is_top and exclude:
            dirnames.remove(exclude)
        for filename in filenames:
            if filename.endswith(ext):
                paths.append(os.path.join(dirpath, filename))
        is_top = False
    return paths


class Extractor:

    def __init__(self, decomp_path: str, output_path: str, keep_existing: bool):
        self.decomp_path = decomp_path
        self.output_path = output_path
        self.keep_existing = keep_existing
        self.warnings: list[str] = []
        self.typedefs: dict[str, c_ast.Typedef] = {}
        self.variables: dict[str, c_ast.Node] = {}
        self.funcs: dict[str, c_ast.FuncDecl] = {}
        self.enums: dict[str, c_ast.Enum] = {}
        self.structs: dict[str, c_ast.Struct] = {}
        self.unions: dict[str, c_ast.Union] = {}
        self.locations: dict[str, str] = {}
        self.doc_strs: dict[str, list[str]] = {}
        self.enum_vals: dict[str, int] = {}
        self.sizes: dict[str, int] = {}

    def extract(self, game: str, region: str, cpp_path: str, elf_path: str) -> None:
        self._find_and_process_files(cpp_path)
        self._compute_enum_vals()
        self._find_unnamed_structs_and_unions()
        self._compute_sizes()
        # Parse elf file
        print("Parsing elf file...")
        elf_names = ep.get_entry_names(ep.parse_elf_file(elf_path))
        elf_addrs = {v: k for k, v in elf_names.items()}
        # Update yaml files
        print("Loading existing entries...")
        info = GameInfo(game, source=InfoSource.YAML_UNK)
        print("Updating yaml files...")
        for map_type in MAP_TYPES:
            self._write_entries(map_type, region, info, elf_names, elf_addrs)
        self._log_warnings()
    
    def _log_warnings(self) -> None:
        if self.warnings:
            with open("_log.txt", "w") as f:
                for msg in self.warnings:
                    f.write(msg + "\n\n")

    def _add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    # -------- Process files --------

    def _find_and_process_files(self, cpp_path: str) -> None:
        """Finds all header and source files, and parses them to get AST nodes
        and docstrings for all declarations/definitions."""
        # Find all .h and .c files
        include_path = os.path.join(decomp_path, "include")
        src_path = os.path.join(decomp_path, "src")
        h_files = get_files_with_ext(include_path, ".h")
        c_files = get_files_with_ext(src_path, ".c")
        # h_files = ["decomp/test.h"]
        # c_files = ["decomp/test.c"]
        all_files = [
            (h_files, ".h", self._process_h_file),
            (c_files, ".c", self._process_c_file),
        ]
        # Find declarations in all files
        for files, ext, process_file in all_files:
            file_count = len(files)
            print(f"Processing {ext} files... 0/{file_count}", end="\r")
            for i, path in enumerate(files):
                # Try parsing the file
                try:
                    ast: c_ast.FileAST = parse_file(
                        path, True, cpp_path,
                        ["-E", f"-I{include_path}", "-D__attribute__(x)=", "-D__inline__=", "-Dasm(x)="]
                    )
                except Exception as ex:
                    print(f"Could not parse {path}\n{ex}")
                    continue
                # Read lines to extract docstrings
                with open(path) as f:
                    lines = f.readlines()
                for node in ast.ext:
                    # Skip nodes included from other files
                    # TODO: When is coord None?
                    if node.coord is not None and node.coord.file != path:
                        continue
                    if process_file(node):
                        self._try_get_doc_str(node, lines)
                print(f"Processing {ext} files... {i+1}/{file_count}", end="\r")
                sys.stdout.flush()
            print()

    # TODO: Combine this with process c file
    def _process_h_file(self, node: c_ast.Node) -> bool:
        """Extracts AST nodes from header files."""
        loc = self._get_node_loc(node.coord)
        if isinstance(node, c_ast.Typedef):
            name = node.name
            self.typedefs[name] = node
        elif isinstance(node, c_ast.Decl):
            nt = node.type
            if isinstance(nt, c_ast.FuncDecl):
                name = node.name
                self.funcs[name] = nt
            elif isinstance(nt, c_ast.Enum):
                name = nt.name
                if name:
                    self.enums[name] = nt
                else:
                    self._add_warning(f"enum without a name\n{loc}")
            elif isinstance(nt, c_ast.Struct):
                name = nt.name
                self.structs[name] = nt
            elif isinstance(nt, c_ast.Union):
                name = nt.name
                self.unions[name] = nt
            else:
                name = node.name
                self.variables[name] = nt
        else:
            return False
        self.locations[name] = loc
        return True
    
    def _process_c_file(self, node: c_ast.Node) -> bool:
        """Extracts AST nodes from source files. Locations from source files
        are preferred over locations from header files."""
        loc = self._get_node_loc(node.coord)
        if isinstance(node, c_ast.Typedef):
            self._add_warning(f"typedef in src file\n{loc}")
            self.locations[node.name] = loc
            return True
        elif isinstance(node, c_ast.Decl):
            nt = node.type
            if isinstance(nt, c_ast.FuncDecl):
                if "static" not in node.storage:
                    self._add_warning(f"func decl in src file\n{loc}")
                name = node.name
                self.funcs[name] = nt
            elif isinstance(nt, c_ast.Enum):
                self._add_warning(f"enum decl in src file\n{loc}")
                name = nt.name
                self.enums[name] = nt
            elif isinstance(nt, c_ast.Struct):
                self._add_warning(f"struct decl in src file\n{loc}")
                name = nt.name
                self.structs[name] = nt
            elif isinstance(nt, c_ast.Union):
                self._add_warning(f"union decl in src file\n{loc}")
                name = nt.name
                self.unions[name] = nt
            else:
                name = node.name
                # Don't overwrite var decl with definition (only the decl is needed)
                if name not in self.locations:
                    if "static" not in node.storage:
                        self._add_warning(f"var def without decl\n{loc}")
                    self.variables[name] = nt
            self.locations[name] = loc
            return True
        elif isinstance(node, c_ast.FuncDef):
            name = node.decl.name
            if name not in self.funcs:
                self.funcs[name] = node.decl.type
            self.locations[name] = loc
            return True
        else:
            return False

    def _try_get_doc_str(self, node: c_ast.Node, lines: list[str]) -> str:
        """Checks for a docstring in the lines above a C declaration or definition."""
        if isinstance(node, c_ast.FuncDef):
            node = node.decl
        end = node.coord.line - 2
        # Skip blank lines
        while end >= 0 and lines[end].strip() == "":
            end -= 1
        # Check end of docstring
        if end < 0 or "*/" not in lines[end]:
            return
        # Find start of docstring
        start = end
        while start >= 0 and "/**" not in lines[start]:
            start -= 1
        if start < 0:
            return
        self.doc_strs[node.name] = lines[start:end+1]

    def _get_node_loc(self, coord: plyparser.Coord) -> str:
        """Converts an AST's coord to a string."""
        rel = os.path.relpath(coord.file, self.decomp_path)
        return rel + ":" + str(coord.line)

    def _find_unnamed_structs_and_unions(self) -> None:
        """Finds structs/unions with unnamed structs/unions defined within them."""
        # Create a copy of the values, since the dictionaries will be modified in-place
        structs_and_unions = list(self.structs.values()) + list(self.unions.values())
        for su in structs_and_unions:
            self._find_unnamed_structs_and_unions_helper(su, [])

    def _find_unnamed_structs_and_unions_helper(self,
        node: Union[c_ast.Struct, c_ast.Union],
        names: list[str]
    ) -> None:
        """Recursive helper function to find unnamed structs/unions."""
        names.append(node.name)
        decls: list[c_ast.Decl] = node.decls
        for decl in decls:
            dt = decl.type
            while isinstance(dt, (c_ast.ArrayDecl, c_ast.PtrDecl)):
                dt = dt.type
            if not isinstance(dt, c_ast.TypeDecl):
                continue
            dtt = dt.type
            if isinstance(dtt, (c_ast.Struct, c_ast.Union)) and dtt.name is None:
                new_names = list(names)
                new_names.append(decl.name)
                name = "__".join(new_names)
                dtt.name = name
                self.locations[name] = self._get_node_loc(dtt.coord)
                if isinstance(dtt, c_ast.Struct):
                    self.structs[name] = dtt
                else:
                    self.unions[name] = dtt
                self._find_unnamed_structs_and_unions_helper(dtt, new_names)

    # -------- Computing values --------

    def _compute_sizes(self) -> None:
        """Computes the sizes of variables, structs, and unions."""
        print("Computing sizes...")
        dicts: list[dict[str, c_ast.Node]] = [self.variables, self.structs, self.unions]
        for d in dicts:
            for name, node in d.items():
                try:
                    self.sizes[name] = self._type_size(node)[0]
                except ValueError as e:
                    print(e)

    def _compute_enum_vals(self) -> None:
        """Computes the values of all items in every enum."""
        print("Computing enum values...")
        self.enum_vals = {}
        for enum in self.enums.values():
            val = 0
            vals: c_ast.EnumeratorList = enum.values
            nums: list[c_ast.Enumerator] = vals.enumerators
            for num in nums:
                if num.value is not None:
                    val = self._const_value(num.value)
                self.enum_vals[num.name] = val
                val += 1

    def _const_int_value(self, node: c_ast.Node) -> int:
        return int(self._const_value(node))

    def _const_value(self, node: c_ast.Node) -> Union[int, float]:
        """Recursively computes the value for an AST node that is a constant integer."""
        if isinstance(node, c_ast.Constant):
            if "." in node.value:
                s: str = node.value
                return float(node.value.rstrip("f"))
            else:
                return int(node.value, 0)
        elif isinstance(node, c_ast.ID):
            return self.enum_vals[node.name]
        elif isinstance(node, c_ast.BinaryOp):
            left = self._const_value(node.left)
            right = self._const_value(node.right)
            if node.op == "+":
                return left + right
            elif node.op == "-":
                return left - right
            elif node.op == "*":
                return left * right
            elif node.op == "/":
                return left // right
            elif node.op == "<<":
                return left << right
            elif node.op == "|":
                return left | right
            else:
                raise ValueError(node.op)
        elif isinstance(node, c_ast.UnaryOp):
            if node.op == "sizeof":
                if isinstance(node.expr, c_ast.ID):
                    var = self.variables[node.expr.name]
                    return self._type_size(var)[0]
                elif isinstance(node.expr, c_ast.ArrayRef):
                    id: c_ast.ID = node.expr.name
                    var = self.variables[id.name]
                    if not isinstance(var, c_ast.ArrayDecl):
                        raise ValueError(f"Expected array decl but got {type(var)}")
                    return self._type_size(var.type)[0]
                else:
                    raise ValueError(type(node.expr))
            elif node.op == "-":
                return -self._const_value(node.expr)
            else:
                raise ValueError(node.op)
        elif isinstance(node, c_ast.TernaryOp):
            return self._const_value(node.iftrue)
        elif isinstance(node, c_ast.Cast):
            return self._const_value(node.expr)
        else:
            raise ValueError(type(node))

    def _type_size(self, node: c_ast.Node) -> tuple[int, int]:
        """Computes the size and alignment of the type of an AST node."""
        if isinstance(node, (c_ast.Decl, c_ast.TypeDecl)):
            return self._type_size(node.type)
        elif isinstance(node, c_ast.IdentifierType):
            name = node.names[-1]
            if name in BUILT_IN_TYPES:
                if "long" in node.names:
                    return 8, 4
                size = BUILT_IN_SIZES.get(name)
                if size is not None:
                    return size, size
                return 4, 4 # int by default
            td = self.typedefs.get(name)
            if td is not None:
                return self._type_size(td)
            else:
                raise ValueError(f"Unrecognized type name {name}")
        elif isinstance(node, c_ast.ArrayDecl):
            if node.dim is None:
                return 0, 0 # treat 0 as unknown
            count = self._const_int_value(node.dim)
            size, align = self._type_size(node.type)
            return count * size, align
        elif isinstance(node, c_ast.PtrDecl):
            return 4, 4
        elif isinstance(node, c_ast.Struct):
            return self._struct_size(node)
        elif isinstance(node, c_ast.Union):
            if node.decls is None:
                return self._type_size(self.unions[node.name])
            return max(
                (self._type_size(d) for d in node.decls),
                key=lambda x: x[0]
            )
        elif isinstance(node, c_ast.Typedef):
            return self._type_size(node.type)
        elif isinstance(node, c_ast.FuncDecl):
            raise ValueError("Func decl must be pointer")
        elif isinstance(node, c_ast.Enum):
            raise ValueError("Can't compute size of enum decl")
        else:
            raise ValueError(type(node))

    def _struct_size(self, node: c_ast.Struct) -> tuple[int, int]:
        """Computes the size and alignment of a struct."""
        decls: list[c_ast.Decl] = node.decls
        if decls is None:
            return self._struct_size(self.structs[node.name])
        bits = 0
        for decl in decls:
            if decl.bitsize is None:
                ds, da = self._type_size(decl)
                remain = bits % (da * 8)
                if remain != 0:
                    bits += (da * 8) - remain
                bits += ds * 8
            else:
                bits += self._const_value(decl.bitsize)
        # Align to 4 bytes (32 bits)
        remain = bits % 32
        if remain != 0:
            bits += 32 - remain
        return bits // 8, 4

    # -------- Declaration string --------

    def _decl_str_and_count(self, node: c_ast.Node) -> tuple[str, int]:
        count = None
        if isinstance(node, c_ast.ArrayDecl):
            # TODO: Proper handling for arrays without a length
            if node.dim is not None:
                count = self._const_int_value(node.dim)
            else:
                count = 0
            node = node.type
        decl = self._decl_str(node)
        return decl, count

    def _decl_str(self, node: c_ast.Node) -> str:
        return self._sub_decl_str(node, "")

    def _type_decl_str(self, node: c_ast.TypeDecl, decl: str) -> str:
        nt = node.type
        if isinstance(nt, c_ast.IdentifierType):
            tn = " ".join(nt.names)
        elif isinstance(nt, c_ast.Struct):
            tn = f"struct {nt.name}"
        elif isinstance(nt, c_ast.Union):
            tn = f"union {nt.name}"
        elif isinstance(nt, c_ast.PtrDecl):
            # Can occur in func params
            return self._ptr_decl_str(nt, decl)
        elif isinstance(nt, c_ast.ArrayDecl):
            # Can occur in func params
            return self._array_decl_str(nt, decl)
        elif isinstance(nt, c_ast.TypeDecl):
            # Can occur in func params
            return self._type_decl_str(nt, decl)
        else:
            raise ValueError(type(nt))
        parts = list(node.quals)
        parts.append(tn)
        spec_str = " ".join(parts)
        if decl:
            spec_str += decl if decl[0] == "*" else " " + decl
        return spec_str

    def _ptr_decl_str(self, node: c_ast.PtrDecl, decl: str) -> str:
        parts = ["*"]
        parts += node.quals
        ptr_str = " ".join(parts)
        if decl:
            if ptr_str[-1] == "*" and decl[0] == "*":
                ptr_str += decl
            else:
                ptr_str += " " + decl
        nt = node.type
        if isinstance(nt, (c_ast.ArrayDecl, c_ast.FuncDecl)):
            ptr_str = "(" + ptr_str + ")"
        return self._sub_decl_str(nt, ptr_str)

    def _array_decl_str(self, node: c_ast.ArrayDecl, decl: str) -> str:
        dim_str = ""
        if node.dim is not None:
            dim_str = f"0x{self._const_int_value(node.dim):X}"
        arr_str = "[" + dim_str + "]"
        return self._sub_decl_str(node.type, decl + arr_str)

    def _func_decl_str(self, node: c_ast.FuncDecl, decl: str) -> str:
        param_str = ""
        if node.args:
            param_str = ", ".join(self._decl_str(p) for p in node.args)
        param_str = "(" + param_str + ")"
        return self._sub_decl_str(node.type, decl + param_str)

    def _typename_str(self, node: c_ast.Typename, decl: str) -> str:
        # Assume this is a param
        assert decl == "" and node.name is None
        return self._sub_decl_str(node.type, "")

    DECL_STR_FUNCS = {
        c_ast.Typedef: _type_decl_str,
        c_ast.Decl: _type_decl_str,
        c_ast.TypeDecl: _type_decl_str,
        c_ast.PtrDecl: _ptr_decl_str,
        c_ast.ArrayDecl: _array_decl_str,
        c_ast.FuncDecl: _func_decl_str,
        c_ast.Typename: _typename_str,
    }

    def _sub_decl_str(self, node: c_ast.Node, decl: str) -> str:
        func = self.DECL_STR_FUNCS[type(node)]
        return func(self, node, decl)

    # -------- Entry writing --------

    def _parse_doc_str(self, name: str) -> tuple[str, dict[str, str], str]:
        """Returns tuple of brief, params, and return."""
        briefs = []
        params = {}
        ret = None
        doc_lines = self.doc_strs.get(name)
        if doc_lines:
            for line in doc_lines:
                # param
                m = DOC_STR_PARAM.search(line)
                if m:
                    params[m.group(1)] = m.group(2).rstrip()
                    continue
                # return
                m = DOC_STR_RETURN.search(line)
                if m:
                    ret = m.group(1).rstrip()
                    continue
                # brief
                m = DOC_STR_BRIEF.search(line)
                if not m:
                    m = DOC_STR_LINE.search(line)
                    if not m:
                        continue
                brief = m.group(1).rstrip()
                m = DOC_STR_ADDR_SIZE.search(brief)
                if m:
                    brief = m.group(1)
                briefs.append(brief)
        brief = " ".join(briefs) if briefs else None
        return brief, params, ret

    def _write_entries(self,
        map_type: str,
        region: str,
        info: GameInfo,
        elf_names: dict[int, str],
        elf_addrs: dict[str, int]
    ) -> None:
        # Get the existing info entries (list) and decomp entries (dict)
        if map_type == MAP_RAM:
            existing = info.ram
            decomp_entries = {k: v for k, v in self.variables.items() if k[0] == "g" and k[1].isupper()}
        elif map_type == MAP_DATA:
            existing = info.data
            decomp_entries = {k: v for k, v in self.variables.items() if k[0] == "s"}
        elif map_type == MAP_CODE:
            existing = info.code
            decomp_entries = self.funcs
        elif map_type == MAP_ENUMS:
            existing = info.enums.values()
            decomp_entries = self.enums
        elif map_type == MAP_STRUCTS:
            existing = info.structs.values()
            decomp_entries = self.structs
        elif map_type == MAP_UNIONS:
            existing = []
            decomp_entries = self.unions
        elif map_type == MAP_TYPEDEFS:
            existing = []
            decomp_entries = self.typedefs
        entries: defaultdict[str, list[DataEntry]] = defaultdict(list)
        remaining_decomp = set(decomp_entries.keys())
        existing_missing_from_elf: set[str] = set()
        decomp_missing_from_elf: set[str] = set()
        existing_missing_from_decomp: set[str] = set()
        # Go through each existing entry
        for entry in existing:
            # Get the filename for this entry
            filename = map_type
            if map_type == MAP_DATA:
                if entry.cat is not None:
                    filename = CAT_TO_STR[entry.cat]
            elif map_type == MAP_CODE:
                if entry.loc and "sprites_AI" in entry.loc:
                    filename = "sprite_ai"
            # Get name of entry
            name = entry.name
            if map_type == MAP_RAM or map_type == MAP_DATA or map_type == MAP_CODE:
                # Get address for this region
                addr = entry.addr
                if isinstance(addr, dict):
                    r_addr = addr.get(region)
                    if r_addr is None:
                        # Include entries that aren't in this region
                        entries[filename].append(entry)
                        continue
                else:
                    r_addr = addr
                # Get name from elf symbols
                name = elf_names.get(r_addr)
                if name is None:
                    existing_missing_from_elf.add(entry.name)
                    if self.keep_existing:
                        entries[filename].append(entry)
                    continue
            # Get AST node
            node = decomp_entries.get(name)
            if node is None:
                existing_missing_from_decomp.add(name)
                if self.keep_existing:
                    entries[filename].append(entry)
                continue
            # Get docstrings (if any) and location
            brief, param_docs, ret_doc = self._parse_doc_str(name)
            loc = self.locations[name]
            # Create new entry using info from existing entry
            if map_type == MAP_RAM or map_type == MAP_DATA:
                decl, count = self._decl_str_and_count(node)
                new_entry = DataEntry(
                    name, brief, decl, count,
                    addr, loc, entry.cat, entry.comp, entry.enum
                )
            elif map_type == MAP_CODE:
                params, ret = self._create_params_and_ret(node, param_docs, ret_doc, entry)
                new_entry = CodeEntry(
                    name, brief, addr, entry.size,
                    entry.mode, params, ret, loc
                )
            elif map_type == MAP_ENUMS:
                vals = self._create_enum_vals(node)
                new_entry = EnumEntry(name, brief, vals, loc)
            elif map_type == MAP_STRUCTS:
                size = self.sizes[name]
                vars = self._create_struct_vars(node, entry)
                new_entry = StructEntry(name, brief, size, vars, loc)
            elif map_type == MAP_UNIONS:
                size = self.sizes[name]
                vars = self._create_union_vars(node, entry)
                new_entry = UnionEntry(name, brief, size, vars, loc)
            entries[filename].append(new_entry)
            remaining_decomp.remove(name)
        # Go through each decomp entry that didn't already exist
        for name in remaining_decomp:
            # Get address from elf symbols (if RAM, data, or code)
            if map_type == MAP_RAM or map_type == MAP_DATA or map_type == MAP_CODE:
                r_addr = elf_addrs.get(name)
                if r_addr is None:
                    decomp_missing_from_elf.add(name)
                    continue
                if map_type == MAP_RAM and info.game == GAME_ZM:
                    addr = r_addr
                else:
                    addr = {region: r_addr}
            # Get AST node, docstrings, and location
            node = decomp_entries[name]
            brief, param_docs, ret_doc = self._parse_doc_str(name)
            loc = self.locations[name]
            # Get the filename for this entry
            filename = map_type
            if map_type == MAP_CODE:
                if "sprites_AI" in loc:
                    filename = "sprite_ai"
            # Create new entry
            if map_type == MAP_RAM or map_type == MAP_DATA:
                decl, count = self._decl_str_and_count(node)
                new_entry = DataEntry(
                    name, brief, decl,
                    count, addr, loc
                )
            elif map_type == MAP_CODE:
                # TODO: Get function size
                params, ret = self._create_params_and_ret(node, param_docs, ret_doc, None)
                new_entry = CodeEntry(
                    name, brief, addr, 0,
                    CodeMode.Thumb, params, ret, loc
                )
            elif map_type == MAP_ENUMS:
                vals = self._create_enum_vals(node)
                new_entry = EnumEntry(name, brief, vals, loc)
            elif map_type == MAP_STRUCTS:
                size = self.sizes[name]
                vars = self._create_struct_vars(node, None)
                new_entry = StructEntry(name, brief, size, vars, loc)
            elif map_type == MAP_UNIONS:
                size = self.sizes[name]
                vars = self._create_union_vars(node, None)
                new_entry = UnionEntry(name, brief, size, vars, loc)
            elif map_type == MAP_TYPEDEFS:
                decl = self._decl_str(node)
                new_entry = TypedefEntry(name, None, decl, loc)
            entries[filename].append(new_entry)
        # Write entries to yaml files
        if self.output_path is None:
            # Overwrite existing
            map_dir = os.path.join(YAML_PATH, info.game, map_type)
        else:
            # Use provided path (create directories if necessary)
            map_dir = os.path.join(self.output_path, map_type)
            Path(map_dir).mkdir(parents=True, exist_ok=True)
        for filename, data in entries.items():
            data.sort()
            path = os.path.join(map_dir, filename + YAML_EXT)
            ifu.write_info_file(path, map_type, data)
        # Add warnings
        if existing_missing_from_elf:
            items = ", ".join(existing_missing_from_elf)
            self._add_warning(f"existing {map_type} entries missing from elf:\n{items}")
        if decomp_missing_from_elf:
            items = ", ".join(decomp_missing_from_elf)
            self._add_warning(f"decomp {map_type} entries missing from elf:\n{items}")
        if existing_missing_from_decomp:
            items = ", ".join(existing_missing_from_decomp)
            self._add_warning(f"existing {map_type} entries missing from decomp:\n{items}")

    def _create_params_and_ret(self,
        node: c_ast.FuncDecl,
        param_docs: dict[str, str],
        ret_doc: str,
        entry: CodeEntry
    ) -> tuple[list[NamedVarEntry], VarEntry]:
        # Create params
        params: list[NamedVarEntry] = None
        entry_params: list[NamedVarEntry] = None
        if entry and entry.params:
            entry_params = entry.params
        pl: c_ast.ParamList = node.args
        # Check if not void
        if not isinstance(pl.params[0], c_ast.Typename):
            params = []
            ps: list[c_ast.Decl] = pl.params
            for i, p in enumerate(ps):
                desc = param_docs.get(p.name)
                ds, count = self._decl_str_and_count(p)
                pe = NamedVarEntry(p.name, desc, ds, count)
                if entry_params and i < len(entry_params):
                    pe.cat = entry_params[i].cat
                    pe.comp = entry_params[i].comp
                    pe.enum = entry_params[i].enum
                params.append(pe)
        # Create ret
        ret: VarEntry = None
        # Check if not void
        ds, count = self._decl_str_and_count(node.type)
        if ds != "void":
            ret = VarEntry(ret_doc, ds, count)
            if entry and entry.ret:
                ret.cat = entry.ret.cat
                ret.comp = entry.ret.comp
                ret.enum = entry.ret.enum
        return params, ret

    def _create_struct_vars(self,
        node: c_ast.Struct,
        entry: StructEntry
    ) -> list[StructVarEntry]:
        # Create dictionary of existing vars based on bit offset
        existing: dict[int, StructVarEntry] = None
        if entry:
            existing = {}
            prev_offset = 0
            extra_bits = 0
            for v in entry.vars:
                if v.offset != prev_offset:
                    prev_offset = v.offset
                    extra_bits = 0
                existing[v.offset * 8 + extra_bits] = v
                extra_bits += v.bits or 0
        decls: list[c_ast.Decl] = node.decls
        bits = 0
        vars: list[StructVarEntry] = []
        for decl in decls:
            ds, count = self._decl_str_and_count(decl.type)
            bitsize = self._const_value(decl.bitsize) if decl.bitsize else None
            # Update bits offset
            if bitsize is None:
                ts, ta = self._type_size(decl)
                remain = bits % (ta * 8)
                if remain != 0:
                    bits += (ta * 8) - remain
                new_bits = bits + (ts * 8)
            else:
                new_bits = bits + bitsize
            offset = bits // 8
            new_ve = StructVarEntry(decl.name, None, ds, count, offset, bitsize)
            if existing and bits in existing:
                ve = existing[bits]
                new_ve.cat = ve.cat
                new_ve.comp = ve.comp
                new_ve.enum = ve.enum
            vars.append(new_ve)
            bits = new_bits
        return vars

    def _create_union_vars(self,
        node: c_ast.Union,
        entry: UnionEntry
    ) -> list[NamedVarEntry]:
        vars: list[NamedVarEntry] = []
        existing: dict[str, NamedVarEntry] = None
        if entry:
            existing = {v.name: v for v in entry.vars}
        decls: list[c_ast.Decl] = node.decls
        for decl in decls:
            ds, count = self._decl_str_and_count(decl.type)
            new_ve = NamedVarEntry(decl.name, None, ds, count)
            if existing and decl.name in existing:
                ve = existing[decl.name]
                new_ve.cat = ve.cat
                new_ve.comp = ve.comp
                new_ve.enum = ve.enum
            vars.append(new_ve)
        return vars

    def _create_enum_vals(self, node: c_ast.Enum) -> list[EnumValEntry]:
        ev: c_ast.EnumeratorList = node.values
        vals: list[EnumValEntry] = []
        nums: list[c_ast.Enumerator] = ev.enumerators
        for num in nums:
            val = self.enum_vals[num.name]
            vals.append(EnumValEntry(num.name, None, val))
        return vals


if __name__ == "__main__":
    parser = argparse.ArgumentParser("Dump AST")
    parser.add_argument("game", type=str)
    parser.add_argument("region", type=str)
    parser.add_argument("decomp_path", type=str,
        help="Path to root directory of decomp (mf or mzm)")
    parser.add_argument("elf_path", type=str)
    parser.add_argument("-cpp", "--cpp_path", type=str, default="gcc")
    parser.add_argument("-o", "--output_path", type=str, default=None,
        help="Output directory for yaml files (omitting this will overwrite existing yaml files)")
    parser.add_argument("-k", "--keep_existing", action="store_true",
        help="Keeps existing entries that aren't found in the decomp")

    args = parser.parse_args()
    game = args.game.lower()
    region = args.region.upper()
    decomp_path = args.decomp_path
    elf_path = args.elf_path
    cpp_path = args.cpp_path
    output_path = args.output_path
    keep_existing = args.keep_existing
    
    extractor = Extractor(decomp_path, output_path, keep_existing)
    extractor.extract(game, region, cpp_path, elf_path)
