import argparse
from collections import defaultdict
import os
import re

from pycparser import c_ast, parse_file, plyparser

from constants import *
import decomp.elf_parser as ep
from game_info import GameInfo, InfoSource
from info_entry import *
import info_file_utils as ifu


# Find defs in .h files (typedefs, vars, funcs, enums, structs, unions)
# - names, types, fields, (partial) sizes, locations
# Prefer locations from .c files (for funcs and rom data)
# Extract docstrings above each location, if any (prefer .c files)
# Compute sizes of structs and vars, using typedefs and evaluating statements
# Parse elf file to get addresses and sizes
# Load existing info entries
# Update entry fields (except for cat, comp, enum, and refs)

BUILT_INT_TYPES = {
    "void", "char", "short", "int", "long",
    "float", "double", "signed", "unsigned"
}

BUILT_IN_SIZES = {
    "char": 1,
    "short": 2,
    "int": 4,
    "float": 4,
    "double": 8
}


DOC_STR_BRIEF = re.compile(r"@brief\s+(.+)")
DOC_STR_PARAM = re.compile(r"@param\s+(\w+)\s+(.+)")
DOC_STR_RETURN = re.compile(r"@return\s+(.+)")
DOC_STR_LINE = re.compile(r"\*\s+(.+)")
DOC_STR_ADDR_SIZE = re.compile(r"\w+\s*\|\s*\w+\s*\|\s*(.+)")


def get_files_with_ext(dir: str, ext: str, exclude: str = None) -> list[str]:
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

    def __init__(self, decomp_path: str):
        self.decomp_path = decomp_path
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

    def extract(self, game: str, region: str, cpp_path: str, elf_path: str) -> None:
        self._find_and_process_files(cpp_path)
        self._compute_enum_vals()
        # Compute sizes of variables, structs, and unions
        print("Computing sizes...")
        sizes: dict[str, int] = {}
        dicts: list[dict[str, c_ast.Node]] = [self.variables, self.structs, self.unions]
        for d in dicts:
            for name, node in d.items():
                try:
                    sizes[name] = self._type_size(node)[0]
                except ValueError as e:
                    print(e)
                    print(node)
                    input()
        # Parse elf file
        print("Parsing elf file...")
        elf_names = ep.get_entry_names(ep.parse_elf_file(elf_path))
        elf_addrs = {v: k for k, v in elf_names.items()}
        # Update yaml files
        print("Updating yaml files...")
        info = GameInfo(game, source=InfoSource.YAML_UNK)
        #self._write_data_entries(True, region, info, elf_names, elf_addrs)
        self._write_data_entries(False, region, info, elf_names, elf_addrs)
        # Funcs
        # Enums
        # Structs
        # Unions

    def _add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    # -------- Process files --------

    def _find_and_process_files(self, cpp_path: str) -> None:
        """Finds all header and source files, and parses them to get AST nodes
        and docstrings for all declarations/definitions."""
        # Find all .h and .c files
        include_path = os.path.join(decomp_path, "include")
        src_path = os.path.join(decomp_path, "src")
        #h_files = get_files_with_ext(include_path, ".h", "libgcc")
        #c_files = get_files_with_ext(src_path, ".c", "libgcc")
        h_files = ["decomp/test.h"]
        c_files = ["decomp/test.c"]
        # Find declarations in all files
        for files in [h_files, c_files]:
            if files[0].endswith(".h"):
                print("Processing .h files...")
                process_file = self._process_h_file
            elif files[0].endswith(".c"):
                print("Processing .c files...")
                process_file = self._process_c_file
            else:
                raise ValueError()
            for path in files:
                # Try parsing the file
                try:
                    ast: c_ast.FileAST = parse_file(
                        path, True, cpp_path,
                        ["-E", f"-I{include_path}", "-D__attribute__(x)=", "-D__inline__="]
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

    def _process_h_file(self, node: c_ast.Node) -> bool:
        """Extracts AST nodes from header files."""
        if isinstance(node, c_ast.Typedef):
            self.typedefs[node.name] = node
        elif isinstance(node, c_ast.Decl):
            nt = node.type
            if isinstance(nt, c_ast.FuncDecl):
                self.funcs[node.name] = nt
            elif isinstance(nt, c_ast.Enum):
                self.enums[nt.name] = nt
            elif isinstance(nt, c_ast.Struct):
                self.structs[nt.name] = nt
            elif isinstance(nt, c_ast.Union):
                self.unions[nt.name] = nt
            else:
                self.variables[node.name] = nt
        else:
            return False
        self.locations[node.name] = self._get_node_loc(node.coord)
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
                self._add_warning(f"func decl in src file\n{loc}")
                self.funcs[node.name] = nt
            elif isinstance(nt, c_ast.Enum):
                self._add_warning(f"enum decl in src file\n{loc}")
                self.enums[nt.name] = nt
            elif isinstance(nt, c_ast.Struct):
                self._add_warning(f"struct decl in src file\n{loc}")
                self.structs[nt.name] = nt
            elif isinstance(nt, c_ast.Union):
                self._add_warning(f"union decl in src file\n{loc}")
                self.unions[nt.name] = nt
            else:
                # Don't overwrite var decl with definition (only the decl is needed)
                if node.name not in self.locations:
                    self._add_warning(f"var def without decl\n{loc}")
                    self.variables[node.name] = nt
            self.locations[node.name] = loc
            return True
        elif isinstance(node, c_ast.FuncDef):
            self.locations[node.decl.name] = loc
            return True
        else:
            return False

    def _try_get_doc_str(self, node: c_ast.Node, lines: list[str]) -> str:
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
        rel = os.path.relpath(coord.file, self.decomp_path)
        return rel + ":" + str(coord.line)

    # -------- Computing values --------

    def _const_value(self, node: c_ast.Node) -> int:
        if isinstance(node, c_ast.Constant):
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

    def _compute_enum_vals(self) -> None:
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

    def _type_size(self, node: c_ast.Node) -> tuple[int, int]:
        """Returns size, alignment"""
        if isinstance(node, (c_ast.Decl, c_ast.TypeDecl)):
            return self._type_size(node.type)
        elif isinstance(node, c_ast.IdentifierType):
            name = node.names[-1]
            if name in BUILT_INT_TYPES:
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
            count = self._const_value(node.dim)
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
        remain = bits % 32
        if remain != 0:
            bits += 32 - remain
        return bits // 8, 4

    # -------- Declaration string --------

    def _decl_str_and_count(self, node: c_ast.Node) -> tuple[str, int]:
        count = None
        if isinstance(node, c_ast.ArrayDecl):
            count = self._const_value(node.dim)
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
        else:
            raise ValueError(type(nt))
        parts = list(node.quals)
        parts.append(tn)
        parts.append(decl)
        return " ".join(parts)

    def _ptr_decl_str(self, node: c_ast.PtrDecl, decl: str) -> str:
        parts = list(node.quals)
        ptr_str = "*" + decl
        nt = node.type
        if isinstance(nt, (c_ast.ArrayDecl, c_ast.FuncDecl)):
            ptr_str = "(" + ptr_str + ")"
        parts.append(ptr_str)
        return self._sub_decl_str(nt, " ".join(parts))

    def _array_decl_str(self, node: c_ast.ArrayDecl, decl: str) -> str:
        dim_str = ""
        if node.dim is not None:
            dim_str = str(self._const_value(node.dim))
        arr_str = "[" + dim_str + "]"
        return self._sub_decl_str(node.type, decl + arr_str)

    def _func_decl_str(self, node: c_ast.FuncDecl, decl: str) -> str:
        param_str = ""
        if node.args:
            param_str = ", ".join(self._decl_str(p) for p in node.args)
        param_str = "(" + param_str + ")"
        return self._sub_decl_str(node.type, decl + param_str)

    DECL_STR_FUNCS = {
        c_ast.TypeDecl: _type_decl_str,
        c_ast.PtrDecl: _ptr_decl_str,
        c_ast.ArrayDecl: _array_decl_str,
        c_ast.FuncDecl: _func_decl_str
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

    def _write_data_entries(self,
        is_ram: bool,
        region: str,
        info: GameInfo,
        elf_names: dict[int, str],
        elf_addrs: dict[str, int]
    ) -> None:
        if is_ram:
            prefix = "g"
            existing = info.ram
            map_type = MAP_RAM
        else:
            prefix = "s"
            existing = info.data
            map_type = MAP_DATA
        entries: defaultdict[str, list[DataEntry]] = defaultdict(list)
        remaining = {n for n in self.variables.keys() if n.startswith(prefix)}
        missing_from_elf: set[str] = set()
        missing_from_decomp: set[str] = set()
        for entry in existing:
            filename = map_type
            if not is_ram and entry.cat is not None:
                filename = CAT_TO_STR[entry.cat]
            # Get address for this region
            addr = entry.addr
            if isinstance(addr, dict):
                r_addr = addr.get(region)
                if r_addr is None:
                    entries[filename].append(entry)
                    continue
            else:
                r_addr = addr
            # Get name from elf symbols
            name = elf_names.get(r_addr)
            if name is None:
                missing_from_elf.add(entry.name)
                continue
            # Get AST node
            node = self.variables.get(name)
            if node is None:
                missing_from_decomp.add(name)
                continue
            brief, _, _ = self._parse_doc_str(name)
            decl, count = self._decl_str_and_count(node)
            loc = self.locations[name]
            new_entry = DataEntry(
                name, brief,
                decl, count,
                addr, loc, entry.cat,
                entry.comp, entry.enum
            )
            entries[filename].append(new_entry)
            remaining.remove(name)
        for name in remaining:
            # Get address from elf symbols
            r_addr = elf_addrs.get(name)
            if r_addr is None:
                missing_from_elf.add(name)
                continue
            if is_ram and info.game == GAME_ZM:
                addr = r_addr
            else:
                addr = {region: r_addr}
            node = self.variables[name]
            brief, _, _ = self._parse_doc_str(name)
            decl, count = self._decl_str_and_count(node)
            loc = self.locations[name]
            new_entry = DataEntry(
                name, brief,
                decl, count,
                addr, loc
            )
            entries[map_type].append(new_entry)
        map_dir = os.path.join(YAML_PATH, info.game, map_type)
        for filename, data in entries.items():
            path = os.path.join(map_dir, "_" + filename + "2.yml")
            ifu.write_info_file(path, map_type, data)

    def _write_code_entries(self,
        region: str,
        info: GameInfo,
        elf_names: dict[int, str],
        elf_addrs: dict[str, int]
    ) -> None:
        entries: defaultdict[str, list[DataEntry]] = defaultdict(list)
        remaining = set(self.funcs.keys())
        missing_from_elf: set[str] = set()
        missing_from_decomp: set[str] = set()
        for entry in info.code:
            filename = MAP_CODE
            # if "sprites_AI" in entry.loc:
            #     filename = "sprite_ai"
            # Get address for this region
            addr = entry.addr
            if isinstance(addr, dict):
                r_addr = addr.get(region)
                if r_addr is None:
                    entries[filename].append(entry)
                    continue
            else:
                r_addr = addr
            # Get name from elf symbols
            name = elf_names.get(r_addr)
            if name is None:
                missing_from_elf.add(entry.name)
                continue
            # Get AST node
            node = self.funcs.get(name)
            if node is None:
                missing_from_decomp.add(name)
                continue
            brief, params, ret = self._parse_doc_str(name)
            loc = self.locations[name]
            new_entry = CodeEntry(
                name, brief, addr,
                entry.size, entry.mode,
                "TODO", "TODO",
                loc
            )
            entries[filename].append(new_entry)
            remaining.remove(name)
        for name in remaining:
            # Get address from elf symbols
            r_addr = elf_addrs.get(name)
            if r_addr is None:
                missing_from_elf.add(name)
                continue
            addr = {region: r_addr}
            node = self.variables[name]
            brief, params, ret = self._parse_doc_str(name)
            loc = self.locations[name]
            new_entry = CodeEntry(
                name, brief, addr,
                0, MODE_THUMB,
                "TODO", "TODO",
                loc
            )
            entries[MAP_CODE].append(new_entry)
        map_dir = os.path.join(YAML_PATH, info.game, MAP_CODE)
        for filename, data in entries.items():
            path = os.path.join(map_dir, "_" + filename + "2.yml")
            ifu.write_info_file(path, MAP_CODE, data)

    def _create_var_entry(self) -> VarEntry:
        return VarEntry(
            "NAME", "DESC", "TYPE",
            "COUNT", "CAT", "COMP", "ENUM"
        )


if __name__ == "__main__":
    argparser = argparse.ArgumentParser("Dump AST")
    argparser.add_argument("game", type=str)
    argparser.add_argument("region", type=str)
    argparser.add_argument("decomp_path", type=str,
        help="Path to root directory of decomp (mf or mzm)")
    argparser.add_argument("elf_path", type=str)
    argparser.add_argument("-cpp", "--cpp_path", type=str, default="gcc")
    
    args = argparser.parse_args()
    game = args.game.upper()
    region = args.region.upper()
    decomp_path = args.decomp_path
    elf_path = args.elf_path
    cpp_path = args.cpp_path
    
    extractor = Extractor(decomp_path)
    extractor.extract(game, region, cpp_path, elf_path)
