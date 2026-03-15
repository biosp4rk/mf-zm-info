import argparse
from abc import ABC, abstractmethod
from enum import Enum, auto
import re


BUILT_IN_TYPES = {
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


# -------- AST --------


class TypeSpecKind(Enum):

    BUILT_IN = auto()
    TYPEDEF = auto()
    ENUM = auto()
    STRUCT = auto()
    UNION = auto()

    def is_tag(self) -> bool:
        return (
            self == TypeSpecKind.ENUM or
            self == TypeSpecKind.STRUCT or
            self == TypeSpecKind.UNION
        )


class TypeQual(Enum):

    CONST = auto()
    VOLATILE = auto()


class AssetType(ABC):

    @abstractmethod
    def spec_kind(self) -> TypeSpecKind:
        pass

    @abstractmethod
    def spec_names(self) -> list[str]:
        pass

    @abstractmethod
    def spec_name(self) -> str:
        pass

    @abstractmethod
    def decl_str(self, decl: str = "") -> str:
        pass

    @abstractmethod
    def get_size(self, sizes: dict[str, int], typedefs: dict[str, "AssetType"]) -> int:
        pass

    @abstractmethod
    def get_alignment(self, typedefs: dict[str, "AssetType"]) -> int:
        pass


class SpecifierType(AssetType):

    def __init__(self, names: list[str], kind: TypeSpecKind, quals: list[TypeQual]):
        self.names = names
        self.kind = kind
        self.quals = quals

    def spec_kind(self) -> TypeSpecKind:
        return self.kind

    def spec_names(self) -> list[str]:
        return self.names

    def spec_name(self) -> str:
        return self.names[-1]

    def decl_str(self, decl: str = "") -> str:
        parts = [q.name.lower() for q in self.quals]
        if self.kind.is_tag():
            parts.append(self.kind.name.lower())
        parts += self.spec_names()
        spec_str = " ".join(parts)
        if decl:
            spec_str += decl if decl[0] == "*" else " " + decl
        return spec_str
    
    def get_size(self, sizes: dict[str, int], typedefs: dict[str, AssetType]) -> int:
        if self.kind == TypeSpecKind.BUILT_IN:
            sn = self.spec_names()
            if "long" in sn:
                return 8
            size = BUILT_IN_SIZES.get(sn[-1])
            if size is not None:
                return size
            return 4 # int by default
        elif self.kind == TypeSpecKind.TYPEDEF:
            return typedefs[self.spec_name()].get_size(sizes, typedefs)
        elif self.kind == TypeSpecKind.STRUCT or self.kind == TypeSpecKind.UNION:
            size = sizes.get(self.spec_name())
            if size is not None:
                return size
            ks = self.kind.name.lower()
            raise ValueError(f"Invalid {ks} name {self.spec_name()}")
        elif self.kind == TypeSpecKind.ENUM:
            raise ValueError("Can't compute size of enum")
        else:
            raise RuntimeError()
    
    def get_alignment(self, typedefs: dict[str, AssetType]) -> int:
        if self.kind == TypeSpecKind.BUILT_IN:
            sn = self.spec_names()
            size = BUILT_IN_SIZES.get(sn[-1])
            if size is not None:
                return size
            return 4 # int by default
        elif self.kind == TypeSpecKind.TYPEDEF:
            return typedefs[self.spec_name()].get_alignment(typedefs)
        elif self.kind == TypeSpecKind.STRUCT or self.kind == TypeSpecKind.UNION:
            return 4
        elif self.kind == TypeSpecKind.ENUM:
            raise ValueError("Can't compute alignment of enum")
        else:
            raise RuntimeError()

    def __str__(self) -> str:
        return self.decl_str()


class OuterType(AssetType):

    def __init__(self, inner_type: AssetType):
        self.inner_type = inner_type

    def spec_kind(self) -> TypeSpecKind:
        return self.inner_type.spec_kind()

    def spec_names(self) -> list[str]:
        return self.inner_type.spec_names()

    def spec_name(self) -> str:
        return self.inner_type.spec_name()


class PointerType(OuterType):

    def __init__(self, inner_type: AssetType, quals: list[TypeQual]):
        super().__init__(inner_type)
        self.quals = quals

    def decl_str(self, decl: str = "") -> str:
        parts = ["*"]
        parts += [q.name.lower() for q in self.quals]
        ptr_str = " ".join(parts)
        if decl:
            if ptr_str[-1] == "*" and decl[0] == "*":
                ptr_str += decl
            else:
                ptr_str += " " + decl
        if isinstance(self.inner_type, (ArrayType, FunctionType)):
            ptr_str = f"({ptr_str})"
        return self.inner_type.decl_str(ptr_str)

    def get_size(self, sizes: dict[str, int], typedefs: dict[str, AssetType]) -> int:
        return 4

    def get_alignment(self, typedefs: dict[str, AssetType]) -> int:
        return 4

    def __str__(self) -> str:
        parts = [q.name.lower() for q in self.quals]
        parts.append(f"pointer to {self.inner_type}")
        return " ".join(parts)


class ArrayType(OuterType):

    def __init__(self, inner_type: AssetType, size: int):
        super().__init__(inner_type)
        self.size = size

    def decl_str(self, decl: str = "") -> str:
        arr_str = f"[0x{self.size:X}]"
        return self.inner_type.decl_str(decl + arr_str)

    def get_size(self, sizes: dict[str, int], typedefs: dict[str, "AssetType"]) -> int:
        return self.size * self.inner_type.get_size(sizes, typedefs)

    def get_alignment(self, typedefs: dict[str, AssetType]) -> int:
        return self.inner_type.get_alignment(typedefs)

    def __str__(self) -> str:
        size_str = "" if self.size is None else f" {self.size}"
        return f"array{size_str} of {self.inner_type}"


class FunctionType(OuterType):

    def __init__(self, inner_type: AssetType, params: list[AssetType]):
        super().__init__(inner_type)
        self.params = params

    def decl_str(self, decl: str = "") -> str:
        param_str = ""
        if self.params:
            param_str = ", ".join(p.decl_str() for p in self.params)
        return self.inner_type.decl_str(decl + f"({param_str})")

    def get_size(self, sizes: dict[str, int], typedefs: dict[str, "AssetType"]) -> int:
        raise ValueError("Function types must be pointers")

    def get_alignment(self, typedefs: dict[str, AssetType]) -> int:
        raise ValueError("Function types must be pointers")

    def __str__(self) -> str:
        param_str = ""
        if self.params:
            param_str = ", ".join(str(p) for p in self.params)
            param_str = f" ({param_str})"
        return f"function{param_str} returning {self.inner_type}"


# -------- Tokenizer --------


# TODO: Add TokenName for built-in types
class TokenName(Enum):

    EOS = auto()
    # Identifiers and literals
    IDENT = auto()          # [A-Za-z_][A-Za-z0-9_]*
    INT = auto()            # [0-9][A-Za-z0-9_]*
    # Separators
    L_PAREN = auto()        # (
    R_PAREN = auto()        # )
    L_BRACK = auto()        # [
    R_BRACK = auto()        # ]
    STAR = auto()           # *
    COMMA = auto()          # ,
    # Specifiers and qualifiers
    SPEC_TAG = auto()       # Ex: struct
    TYPE_QUAL = auto()      # Ex: const
    STORE_SPEC = auto()     # Ex: static


class Token:

    def __init__(self, name: TokenName, text: str):
        self.name = name
        self.text = text
    
    def __str__(self) -> str:
        return f"({self.name.name}, {self.text})"


SINGLE_CHAR_TOKENS = {
    "(": TokenName.L_PAREN,
    ")": TokenName.R_PAREN,
    "[": TokenName.L_BRACK,
    "]": TokenName.R_BRACK,
    "*": TokenName.STAR,
    ",": TokenName.COMMA
}

KEYWORDS = {
    # Specifier tags
    "enum": TokenName.SPEC_TAG,
    "struct": TokenName.SPEC_TAG,
    "union": TokenName.SPEC_TAG,
    # Type qualifiers
    "const": TokenName.TYPE_QUAL,
    "volatile": TokenName.TYPE_QUAL,
    # Storage qualifiers
    "extern": TokenName.STORE_SPEC,
    "static": TokenName.STORE_SPEC,
    "auto": TokenName.STORE_SPEC,
    "register": TokenName.STORE_SPEC
}

class TypeTokenizer:

    def __init__(self):
        self.tokens: list[Token] = None
        self.index: int = None
        self.token_index: int = None
        self.text: str = None

    def tokenize(self, text: str) -> list[Token]:
        self.tokens = []
        self.index = 0
        self.text = text
        while self.index < len(text):
            self.token_index = self.index
            c = text[self.index]
            self.index += 1
            # Skip whitespace
            if c == " ":
                continue
            # Check separator
            name = SINGLE_CHAR_TOKENS.get(c)
            if name is not None:
                self._add_token(name, c)
            # Check integer
            elif re.match(r"[0-9]", c):
                self._add_token(TokenName.INT, self._alpha_num())
            # Check identifier
            elif re.match(r"[A-Za-z_]", c):
                ident = self._alpha_num()
                name = KEYWORDS.get(ident)
                if name is None:
                    name = TokenName.IDENT
                self._add_token(name, ident)
            else:
                raise ValueError(f"Unrecognized character '{c}'")
        self._add_token(TokenName.EOS, "")
        return self.tokens

    def _alpha_num(self) -> str:
        while self.index < len(self.text):
            c = self.text[self.index]
            if re.match(r"[A-Za-z0-9_]", c):
                self.index += 1
            else:
                break
        return self.text[self.token_index : self.index]

    def _add_token(self, name: TokenName, text: str) -> None:
        self.tokens.append(Token(name, text))


# -------- Parser --------


TAG_TYPES = {
    "enum": TypeSpecKind.ENUM,
    "struct": TypeSpecKind.STRUCT,
    "union": TypeSpecKind.UNION
}


class ParseInfo:

    def __init__(self,
        spec: AssetType,
        start: int,
        left: int
    ):
        self.spec = spec
        self.root = spec
        self.outer = None
        self.start = start
        self.left = left
    
    def update_parent_types(self, new_type: OuterType) -> None:
        if self.outer is None:
            self.root = new_type
        else:
            self.outer.inner_type = new_type
        self.outer = new_type


class TypeParser:

    def __init__(self):
        self.tokens: list[Token] = None
        self.index: int = None
        self.curr_token: Token = None
        self.prev_token: Token = None

    def parse(self, tokens: list[Token]) -> AssetType:
        self.tokens = tokens
        self.index = -1
        self.curr_token = None
        self._next_token()
        root = self._parse_decl(0)
        if self.curr_token.name != TokenName.EOS:
            raise ValueError("Expected EOS")
        return root

    def _next_token(self) -> None:
        self.prev_token = self.curr_token
        self.index += 1
        self.curr_token = self.tokens[self.index]

    def _accept(self, name: TokenName) -> bool:
        if self.curr_token.name == name:
            self._next_token()
            return True
        return False

    def _expect(self, name: TokenName) -> None:
        if not self._accept(name):
            raise ValueError(f"Expected {name.name} but got {self.curr_token.name}")

    def _parse_decl(self, start: int) -> AssetType:
        in_param = start > 0
        # First tokens must be type spec
        spec = self._parse_type_spec()
        # Check if already at end
        if self.curr_token.name == TokenName.EOS:
            return spec
        # Update left end index
        start = self.index - 1
        # Find middle of declaration
        self._find_decl_middle()
        left = self.index - 1
        # Parse from middle outwards
        info = ParseInfo(spec, start, left)
        while True:
            if self._accept(TokenName.L_BRACK):
                # Array
                self._expect(TokenName.INT)
                size = int(self.prev_token.text, 0)
                self._expect(TokenName.R_BRACK)
                arr_type = ArrayType(spec, size)
                info.update_parent_types(arr_type)
            elif self._accept(TokenName.L_PAREN):
                # Function
                params: list[AssetType] = []
                if not self._accept(TokenName.R_PAREN):
                    while True:
                        param_type = self._parse_decl(self.index)
                        if self.curr_token.name == TokenName.EOS:
                            raise ValueError("Unexpected EOS while parsing function parameters")
                        params.append(param_type)
                        if self._accept(TokenName.R_PAREN):
                            break
                        self._expect(TokenName.COMMA)
                func_type = FunctionType(spec, params)
                info.update_parent_types(func_type)
            elif self.curr_token.name == TokenName.R_PAREN:
                # End of parentheses
                self._parse_left(info, False)
                if in_param and info.left == start:
                    break
            elif (
                self.curr_token.name == TokenName.EOS or
                self.curr_token.name == TokenName.COMMA
            ):
                # End of declaration (or param)
                self._parse_left(info, True)
                break
            else:
                tn = self.curr_token.name.name
                raise ValueError(f"Unexpected token {tn}")
        return info.root

    def _parse_type_spec(self) -> AssetType:
        quals = []
        while self._accept(TokenName.TYPE_QUAL):
            text = self.prev_token.text.upper()
            quals.append(TypeQual[text])
        if self._accept(TokenName.SPEC_TAG):
            kind = TAG_TYPES[self.prev_token.text]
            self._expect(TokenName.IDENT)
            names = [self.prev_token.text]
        else:
            self._expect(TokenName.IDENT)
            names = [self.prev_token.text]
            if names[0] in BUILT_IN_TYPES:
                kind = TypeSpecKind.BUILT_IN
                while self._accept(TokenName.IDENT):
                    name = self.prev_token.text
                    if name not in BUILT_IN_TYPES:
                        raise ValueError(f"Expected built-in type but got '{name}'")
                    names.append(name)
            else:
                # typedefs should only have one name
                kind = TypeSpecKind.TYPEDEF
        return SpecifierType(names, kind, quals)

    def _find_decl_middle(self) -> None:
        while True:
            if self._accept(TokenName.TYPE_QUAL) or self._accept(TokenName.STAR):
                continue
            if self.curr_token.name == TokenName.L_PAREN:
                next_token = self.tokens[self.index + 1].name
                if next_token != TokenName.R_PAREN and next_token != TokenName.IDENT:
                    self._next_token()
                    continue
            break

    def _parse_left(self, info: ParseInfo, decl_end: bool) -> None:
        quals: list[TypeQual] = []
        while info.left > info.start:
            token = self.tokens[info.left]
            info.left -= 1
            if token.name == TokenName.STAR:
                quals.reverse()
                ptr_type = PointerType(info.spec, quals)
                info.update_parent_types(ptr_type)
                quals = []
            elif token.name == TokenName.TYPE_QUAL:
                text = token.text.upper()
                quals.append(TypeQual[text])
            elif token.name == TokenName.L_PAREN:
                if decl_end:
                    tn = self.curr_token.name.name
                    raise ValueError(f"Unexpected token {tn}")
                else:
                    self._next_token()
                    break
        if quals:
            qs = " ".join([q.name.lower() for q in quals])
            raise ValueError(f"Unexpected type qualifier {qs}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("text", type=str)

    args = parser.parse_args()

    tokenizer = TypeTokenizer()
    parser = TypeParser()

    tokens = tokenizer.tokenize(args.text)
    node = parser.parse(tokens)
    print(node.decl_str())
    print(node)
