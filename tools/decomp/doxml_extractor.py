import argparse
import json
import os
from typing import Any, Union

import decomp.doxmlparser as dxp
import decomp.doxmlparser.compound as dxpc
from decomp.doxmlparser.compound import DoxCompoundKind, DoxMemberKind, MixedContainer


class DcBaseEntry:
    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError()

    def __str__(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class DcTypeDecl(DcBaseEntry):
    """Used for return types."""
    def __init__(self, decl: str, desc: str):
        self.decl = decl
        self.desc = desc
    
    def to_dict(self) -> dict[str, Any]:
        d = {"decl": self.decl}
        if self.desc:
            d["desc"] = self.desc
        return d


class DcNamedTypeDecl(DcTypeDecl):
    """Used for function parameters."""
    def __init__(self, name: str, decl: str, desc: str):
        super().__init__(decl, desc)
        self.name = name

    def to_dict(self) -> dict[str, Any]:
        d = {
            "name": self.name,
            "decl": self.decl
        }
        if self.desc:
            d["desc"] = self.desc
        return d


class DcVarEntry(DcNamedTypeDecl):
    """Used for RAM and ROM variables."""
    def __init__(self, name: str, decl: str, loc: str, desc: str):
        super().__init__(name, decl, desc)
        self.loc = loc

    def to_dict(self) -> dict[str, Any]:
        d = {
            "name": self.name,
            "decl": self.decl,
            "loc": self.loc,
        }
        if self.desc:
            d["desc"] = self.desc
        return d


class DcCodeEntry(DcBaseEntry):
    def __init__(self, name: str, params: list[DcNamedTypeDecl], ret: DcTypeDecl, loc: str, desc: str):
        self.name = name
        self.params = params
        self.ret = ret
        self.loc = loc
        self.desc = desc

    def to_dict(self) -> dict[str, Any]:
        d = {"name": self.name}
        if self.params:
            d["params"] = [p.to_dict() for p in self.params]
        if self.ret:
            d["ret"] = self.ret.to_dict()
        d["loc"] = self.loc
        if self.desc:
            d["desc"] = self.desc
        return d


def linked_text_to_str(linked_text: dxp.linkedTextType):
    str = ""
    if linked_text:
        for text_or_ref in linked_text.content_:
            if text_or_ref.getCategory() == MixedContainer.CategoryText:
                str += text_or_ref.getValue()
            else:
                str += text_or_ref.getValue().get_valueOf_()
    return str


def is_body_file(item: Union[dxp.compounddefType, dxp.memberdefType]) -> bool:
    loc = item.get_location()
    return loc.get_file() == loc.get_bodyfile()


def get_loc_str(item: Union[dxp.compounddefType, dxp.memberdefType]) -> str:
    loc = item.get_location()
    return f"{loc.get_file()}:{loc.get_line()}"


code_entries = []


def parse_single_text_para(item: Union[dxp.descriptionType, dxp.docSimpleSectType]) -> str:
    """
    Gets the text from an item that should have a single para with plain text.
    Returns None if there are no paras.
    """
    desc_paras: list[dxp.docParaType] = item.get_para()
    if not desc_paras:
        return None
    assert len(desc_paras) == 1
    return desc_paras[0].get_valueOf_().strip()


def parse_doc_param_list(param_list: dxpc.docParamListType) -> dict[str, str]:
    """Returns a dictionary of param names to descriptions."""
    param_descs = {}
    param_items: list[dxp.docParamListItem] = param_list.get_parameteritem()
    for param_item in param_items:
        # Get param description
        desc_str = parse_single_text_para(param_item.get_parameterdescription())
        if not desc_str:
            continue
        # Get param name
        param_name_lists: list[dxp.docParamNameList] = param_item.get_parameternamelist()
        assert len(param_name_lists) == 1
        param_names: list[dxp.docParamName] = param_name_lists[0].get_parametername()
        assert len(param_names) == 1
        param_name = param_names[0].get_valueOf_()
        param_descs[param_name] = desc_str
    return param_descs


def parse_detailed_desc(desc: dxp.descriptionType) -> tuple[str, dict[str, str], str]:
    """Returns a tuple of untagged text, param descriptions, and return description."""
    paras: list[dxp.docParaType] = desc.get_para()
    raw_desc = ""
    param_descs = {}
    ret_desc = None
    for para in paras:
        contents: list[dxpc.MixedContainer] = para.content_
        for content in contents:
            category = content.getCategory()
            value = content.getValue()
            if category == MixedContainer.CategoryNone:
                raise ValueError(type(value))
            elif category == MixedContainer.CategoryText:
                if not value.isspace():
                    raw_desc += value
            elif category == MixedContainer.CategorySimple:
                raise ValueError(type(value))
            elif category == MixedContainer.CategoryComplex:
                if isinstance(value, dxpc.docParamListType):
                    param_descs.update(parse_doc_param_list(value))
                elif isinstance(value, dxpc.docSimpleSectType):
                    ret_desc = parse_single_text_para(value)
                else:
                    raise ValueError(type(value))
    return raw_desc.strip(), param_descs, ret_desc


def parse_function(memberdef: dxp.memberdefType):
    # Skip function defs in header files
    if not is_body_file(memberdef):
        return
    # Get description
    brief_desc = parse_single_text_para(memberdef.get_briefdescription())
    raw_desc, param_descs, ret_desc = parse_detailed_desc(memberdef.get_detaileddescription())
    if not brief_desc:
        brief_desc = raw_desc
    if brief_desc:
        idx = brief_desc.rfind("|")
        if idx != -1:
            brief_desc = brief_desc[idx+1:].lstrip()
    # Get params
    param_entries = []
    params: list[dxp.paramType] = memberdef.get_param()
    for param in params:
        # Get type
        p_type = linked_text_to_str(param.get_type())
        if p_type == "void" and len(params) == 1:
            break
        # Get name
        p_name = param.get_defname()
        if not p_name:
            p_name = param.get_declname()
        p_desc = param_descs.get(p_name)
        param_entries.append(DcNamedTypeDecl(p_name, p_type, p_desc))
    if len(param_entries) == 0:
        param_entries = None
    # Get return value
    ret_entry = None
    ret_type = linked_text_to_str(memberdef.get_type())
    if ret_type and ret_type != "void":
        ret_entry = DcTypeDecl(ret_type, ret_desc)
    # Create code entry
    entry = DcCodeEntry(
        memberdef.get_name(), param_entries, ret_entry,
        get_loc_str(memberdef), brief_desc
    )
    code_entries.append(entry)


def parse_members(compounddef: dxp.compounddefType, sectiondef: dxp.sectiondefType):
    memberdefs: list[dxp.memberdefType] = sectiondef.get_memberdef()
    if compounddef.get_kind() == DoxCompoundKind.STRUCT:
        # TODO: Create struct entry
        for memberdef in memberdefs:
            if memberdef.get_kind() == DoxMemberKind.VARIABLE:
                # Struct variable
                pass
    elif compounddef.get_kind() == DoxCompoundKind.FILE:
        for memberdef in memberdefs:
            if memberdef.get_kind() == DoxMemberKind.FUNCTION:
                #parse_function(memberdef)
                pass
            elif memberdef.get_kind() == DoxMemberKind.VARIABLE:
                # Data (and RAM?) variable
                var_name = memberdef.get_name()
                var_decl = memberdef.get_definition()
                loc = get_loc_str(memberdef)
                print("\t".join([var_name, var_decl, loc]))
                input()


def parse_compound(xml_dir: str, name: str):
    xml_path = os.path.join(xml_dir, name + ".xml")
    root_obj = dxpc.parse(xml_path, True)
    compounddefs: list[dxp.compounddefType] = root_obj.get_compounddef()
    for compounddef in compounddefs:
        sectiondefs: list[dxp.sectiondefType] = compounddef.get_sectiondef()
        for sectiondef in sectiondefs:
            parse_members(compounddef, sectiondef)


def parse_index(xml_dir: str):
    index_path = os.path.join(xml_dir, "index.xml")
    root_obj = dxp.index.parse(index_path, True)
    compounds: list[dxp.CompoundType] = root_obj.get_compound()
    for compound in compounds:
        #print(f"Processing {compound.get_name()} ...")
        parse_compound(xml_dir, compound.get_refid())


if __name__ == "__main__":
    argparser = argparse.ArgumentParser("Dump AST")
    argparser.add_argument("xml_path", type=str,
        help="Path to the directory of the doxygen xml")
    args = argparser.parse_args()

    parse_index(args.xml_path)

    # code_entries.sort(key=lambda x: x.name)
    # for ce in code_entries:
    #     print(ce.name, ce.loc)


# Classes:              5 (0 documented)
# Structs:            179
# Unions:               6
# Namespaces:           7
# Files:             1162 (0 documented)
# Pages:                3
# Methods:             63 (0 documented)
#   Public:            31 (0 documented)
#   Private:           32 (0 documented)
# Functions:         5384 (5057 documented)
# Attributes:        1799 (0 documented)
# Variables:        26640 (6 documented)
# Params:           40723
