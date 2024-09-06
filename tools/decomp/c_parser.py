import argparse
import os

from pycparser import c_ast, parse_file, plyparser

from constants import PRIMITIVES
from decomp.ident_formatter import desc_from_ident, label_from_ident
from info_entry import StructEntry, StructVarEntry
from info_file_utils import obj_to_yaml_str


class DcVarEntry:
    def __init__(self, name: str, decl: str, count: int):
        self.name = name
        self.decl = decl
        self.count = count


class DcCodeEntry:
    def __init__(self, name: str, params: list[DcVarEntry], ret: DcVarEntry, file: str):
        self.name = name
        self.params = params
        self.ret = ret
        self.file = file


# def parse_decl(node: c_ast.Decl):
#     return parse_type_decl(node.type)


def parse_type_decl(node: c_ast.TypeDecl) -> DcVarEntry:
    # Parse derived types (pointer/array) and count
    decl = ""
    count = None
    first = True
    while True:
        if isinstance(node, c_ast.PtrDecl):
            decl = f"*{decl}"
        elif isinstance(node, c_ast.ArrayDecl):
            dim = None if node.dim is None else int(node.dim.value)
            if first:
                count = dim
            else:
                size = "" if dim is None else dim
                decl = f"({decl})[{size}]"
        elif isinstance(node, c_ast.TypeDecl):
            break
        else:
            raise NotImplementedError(f"Unsupported type decl")
        node = node.type
        first = False
    # Get variable name and base type
    name = node.declname
    node_type = node.type
    if isinstance(node_type, c_ast.IdentifierType):
        type_name = node_type.names[0]
    elif isinstance(node_type, c_ast.Struct):
        type_name = node_type.name
    else:
        raise NotImplementedError("Unsupported type")
    decl = f"{type_name}{decl}"
    return DcVarEntry(name, decl, count)


def parse_func_decl(node: c_ast.FuncDecl):
    # Parse type (name and return type)
    ret_entry = parse_type_decl(node.type)
    func_name = ret_entry.name
    if ret_entry.decl == "void":
        ret_entry = None
    else:
        ret_entry.name = None
    # Parse params
    param_entries = None
    if node.args:
        param_entries = []
        for param in node.args:
            # Should be Decl or Typename, both have TypeDecl field
            p_entry = parse_type_decl(param.type)
            param_entries.append(p_entry)
    loc = get_decomp_var_loc(node.coord)
    return DcCodeEntry(func_name, param_entries, ret_entry, loc)


def parse_struct(filename: str, struct_name: str) -> None:
    ast = parse_file(filename, True)
    # find struct definitions
    for child in ast:
        if not isinstance(child, c_ast.Decl):
            continue
        ct = child.type
        if not isinstance(ct, c_ast.Struct):
            continue
        if ct.name != struct_name:
            continue
        # create struct entry
        struct_size = 0
        fields = []
        for decl in ct.decls:
            dt = decl.type
            field_name = dt.declname
            field_type = dt.type.names[0]
            # align if necessary
            field_size = PRIMITIVES[field_type]
            while struct_size % field_size != 0:
                struct_size += 1
            fields.append(StructVarEntry(
                desc_from_ident(field_name),
                label_from_ident(field_name),
                field_type,
                None,
                struct_size
            ))
            struct_size += field_size
        entry = StructEntry(
            desc_from_ident(struct_name),
            label_from_ident(struct_name),
            struct_size,
            fields
        )
        obj = StructEntry.to_obj(entry)
        print(obj_to_yaml_str([obj]))


def search(node: c_ast.Node, cls: type, file: str):
    """Recursively searches the provided ast node for the given type in the given file."""
    for n in node:
        if n.coord is not None and n.coord.file != file:
            continue
        if isinstance(n, cls):
            yield n
        for c in search(n, cls, file):
            yield c


def find(node: c_ast.Node, cls: type) -> c_ast.Node:
    g = search(node, cls)
    return next(g)


def get_decomp_var_loc(coord: plyparser.Coord) -> str:
    items = coord.file.split(os.sep)
    idx = items.index("mzm")
    return os.sep.join(items[idx+1:]) + ":" + str(coord.line)


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


if __name__ == "__main__":
    argparser = argparse.ArgumentParser("Dump AST")
    argparser.add_argument("decomp_path", type=str,
        help="Path to root directory of decomp (mf or mzm)")
    argparser.add_argument("-cpp", "--cpp_path", type=str, default="gcc")
    
    args = argparser.parse_args()
    decomp_path = args.decomp_path
    cpp_path = args.cpp_path
    include_path = os.path.join(decomp_path, "include")
    src_path = os.path.join(decomp_path, "src")

    # Find paths of all function files in src
    src_c_files = get_files_with_ext(src_path, ".c", "data")
    for path in src_c_files:
        try:
            ast: c_ast.Node = parse_file(
                path, True, cpp_path,
                ["-E", f"-I{include_path}", "-D__attribute__(x)=", "-D__inline__="]
            )
            print(f"Parsed {path}")
        except Exception as ex:
            print(f"Could not parse {path}")
            continue
        funcs: list[c_ast.Node] = search(ast, c_ast.FuncDecl, path)
        for f in funcs:
            parse_func_decl(f)
            
