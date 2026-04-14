from typing import Tuple, Union


class AccessSite:
    @classmethod
    def process_line(cls, line, offset) -> Union["AccessSite", None]:
        tokens = line.split("label:")
        if len(tokens) == 1:
            return None
        right_tokens = tokens[1].split()
        if len(right_tokens) != 2:
            raise ValueError(
                "If instruction line has a label it should have another "
                "string specifying the allocation site (scope) for that label."
            )
        pc = int(tokens[0].split(":")[0], 16) + offset
        label = right_tokens[0].split("@")[0]
        allocation_site = right_tokens[1]
        return cls(pc, label, allocation_site)

    def __init__(self, pc: int, label: str, allocation_site: str) -> None:
        self._pc = pc
        self._label = label
        self._allocation_site = allocation_site

    def allocation_site(self) -> str:
        return self._allocation_site

    def pc(self) -> int:
        return self._pc

    def label(self) -> str:
        return self._label

    def __str__(self) -> str:
        return f"AccessSite(pc: {hex(self._pc)}, full_label: {self._allocation_site}_{self._label})"

    def __repr__(self) -> str:
        return str(self)


class Instruction:
    @classmethod
    def process_line(cls, line, offset) -> "Instruction":
        tokens = line.split("label:")

        left_tokens = tokens[0].split(":")
        if len(left_tokens) > 2:
            raise ValueError(
                f"Synatx error before at line {line} before `label:`"
            )
        pc = int(left_tokens[0], 16) + offset
        pneumonic_tokens = left_tokens[1].split()
        inst_tokens = pneumonic_tokens[0].split("@")
        dest_idx_override = -1
        if len(inst_tokens) > 1:
            if len(inst_tokens) > 2:
                raise ValueError(
                    "You can append a pattern like `@[numerical] to the "
                    "instruction pneumonic override destination register index."
                )
            dest_idx_override = int(inst_tokens[1])
        pneumonic_tokens[0] = inst_tokens[0]
        pneumonic = " ".join(pneumonic_tokens)
        if len(tokens) > 1:
            right_tokens = tokens[1].split()
            if len(right_tokens) != 2:
                raise ValueError(
                    "If instruction line has a label it should have another "
                    "string specifying the allocation site (scope) for that label."
                )
            label_tokens = right_tokens[0].split("@")
            if len(label_tokens) > 2:
                raise ValueError(
                    "Your label string should be a two parter separated by @. "
                    "First part can be alphanumerical and the second part should be numerical."
                )
            label = label_tokens[0]
            if len(label_tokens) == 2:
                label_version = int(label_tokens[1])
            else:
                label_version = 0
        else:
            label = "n/a"
            label_version = -1
        return cls(pc, pneumonic, dest_idx_override, label, label_version)

    def __init__(
        self,
        pc: int,
        pneumonic: str,
        dest_idx_override: int,
        label: str,
        label_version: int,
    ) -> None:
        self._pc = pc
        self._pneuomonic = pneumonic
        self._dest_idx_override = dest_idx_override
        self._label = label
        self._label_version = label_version

    def pc(self) -> int:
        return self._pc

    def label(self) -> str:
        return self._label

    def label_version(self) -> int:
        return self._label_version

    def has_override(self) -> bool:
        return self._dest_idx_override != -1

    def override(self) -> Tuple[int, int]:
        return self._pc, self._dest_idx_override

    def __str__(self) -> str:
        return f"Instruction(pc: {hex(self._pc)}, pneumonic: {self._pneuomonic}, label: {self._label}, label_version: {self._label_version})"

    def __repr__(self) -> str:
        return str(self)


def process_snippet(snippet):
    offset = 0
    access_sites = {}
    indirect_chains = []

    current_scope = None
    current_chain = []
    for line_number, line in enumerate(snippet.splitlines()[1:]):
        line_no_comment = line.split("//")[0]
        if line_no_comment.startswith("offset") and line_number != 0:
            raise ValueError(
                "Offset line should only appear at the start of the snippet if at all."
            )
        if line_no_comment.startswith("offset"):
            offset = int(line_no_comment.split(":")[1], 16)
            continue
        if line_no_comment.startswith("func"):
            if current_scope is not None:
                raise RuntimeError(
                    f"Found `func` without having closed prior scope {current_scope}."
                )
            tokens = line_no_comment.split()
            if len(tokens) != 2:
                raise ValueError(
                    f"Function declaration lines should look like `func [name of the function]`."
                )
            current_scope = line_no_comment.split()[1].rstrip(":")
            continue
        if line_no_comment.startswith("ret"):
            tokens = line_no_comment.split()
            if len(tokens) != 2:
                raise ValueError(
                    f"Function termination lines should look like `ret [pc of ret instruction]`."
                )
            ret_pc = int(tokens[1], 16) + offset
            if current_scope in access_sites:
                access_sites[current_scope]["ret"] = ret_pc
            current_scope = None
            continue
        if len(line_no_comment) == 0:
            indirect_chains.append(current_chain)
            current_chain = []
            continue
        if (
            access_site := AccessSite.process_line(line_no_comment, offset)
        ) is not None:
            if access_site.allocation_site() not in access_sites:
                access_sites[access_site.allocation_site()] = {
                    "ret": -1,
                    "access_sites": [],
                }
            access_sites[access_site.allocation_site()]["access_sites"].append(
                access_site
            )
        current_chain.append(Instruction.process_line(line_no_comment, offset))

    return access_sites, indirect_chains
