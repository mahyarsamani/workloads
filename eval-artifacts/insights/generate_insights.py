#!/usr/bin/env python3
"""Write insights_snippet.txt next to m5.cpt in ROI checkpoints.

Each checkpoint gets the snippet of the binary its guest ran
(workloads/eval-artifacts/insights/<binary>.snippet), after the snippet is
checked against that checkpoint:
  - the snippet header names this binary, this checkpoint ("applies to"), and
    the disk image and kernel md5 of the checkpoint's manifest;
  - the md5 of the checkpoint's disassembly (process_info.txt up to the first
    `PID:` line) matches the header, and every rank's memory map loads the
    binary at the snippet's `offset`;
  - every instruction line names the instruction the disassembly has at that
    PC, and every `ret` PC is a `ret` or an unconditional branch (tail call);
  - the parsed chains are ones the O3 CPU can register: at least two
    instructions, labelled at both ends, one role per PC, unique relation
    names.
A checkpoint that fails any check is refused and nothing is written for it.
hov checkpoints are skipped: their indirect accesses run through the libhov
trampolines, so PC-keyed snippets cannot describe them.

With --se, the SE binaries' snippets (se/<binary dir>_<binary>.snippet) are
checked against the binaries their headers name (md5, instructions, exits,
chains, offset 0) instead; SE runs read them from there, so nothing is
written. A labelled line on its own labels a direct access (no chain).

usage: generate_insights.py [--check] [--snippets DIR] [CHECKPOINT_DIR ...]
       generate_insights.py --se
  With no directory, every checkpoint under workloads/eval-artifacts/checkpoints
  and workloads/additional-checkpoints is processed. With --check, the existing
  insights_snippet.txt files are compared instead of written. --snippets picks
  the directory of <binary>.snippet files: this directory by default (the
  campaign's images), v2/ for the v2 images (checkpoints-v2).
Exits non-zero if any checkpoint is refused (or differs, with --check).
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

INSIGHTS_DIR = Path(__file__).resolve().parent
EVAL_ARTIFACTS_DIR = INSIGHTS_DIR.parent
WORKLOADS_DIR = EVAL_ARTIFACTS_DIR.parent
# NOTE: The snippet headers name checkpoints as <parent dir name>/<name>, so
# these directories keep their names: checkpoints, additional-checkpoints.
CHECKPOINT_DIRS = [
    EVAL_ARTIFACTS_DIR / "checkpoints",
    WORKLOADS_DIR / "additional-checkpoints",
]
MANIFEST_NAME = "checkpoint_manifest.json"
PROCESS_INFO_NAME = "process_info.txt"
SNIPPET_NAME = "insights_snippet.txt"

# NOTE: Import the parser as a plain module: the workloads package's
# __init__ imports gem5, which is not available outside a gem5 run.
sys.path.insert(0, str(WORKLOADS_DIR))
from workload_insights import process_snippet, read_header  # noqa: E402

# The SE binaries' snippets (se/<binary dir>_<binary>.snippet), checked
# against the binaries themselves: gem5 SE reads them straight from here
# (SEWorkloadWrapper.insights_snippet), so there is nothing to write.
SE_SNIPPETS_DIR = INSIGHTS_DIR / "se"
OBJDUMP = "aarch64-linux-gnu-objdump"


class Refused(Exception):
    pass


def binary_name(workload: dict) -> str:
    """The guest binary for a manifest's workload dict, named as the
    workload wrappers name it."""
    name, variant = workload["name"], workload["variant"]
    if name == "ume":
        return f"ume_mpi_{workload['region']}_{variant}"
    if name == "hpcg":
        return f"xhpcg_{workload['kernel']}_{variant}_gem5fs"
    if name == "branson":
        return f"BRANSON_{variant}"
    raise Refused(f"no binary naming rule for workload {name!r}")


def normalize(text: str) -> str:
    """An instruction's text without comments, symbols and extra spaces."""
    text = text.split("//")[0]
    text = re.sub(r"<[^>]*>", "", text)
    return " ".join(text.replace(",", ", ").split()).replace(" ,", ",")


def read_process_info(path: Path, binary: str):
    """(disassembly md5, {pc: instruction text}, set of load bases)."""
    text = path.read_text(errors="replace")
    disassembly, _, maps = text.partition("\nPID:")
    md5 = hashlib.md5(disassembly.encode()).hexdigest()
    instructions = {}
    line_re = re.compile(r"^\s*([0-9a-f]+):\t[0-9a-f]{8} \t(.*)$")
    for line in disassembly.splitlines():
        m = line_re.match(line)
        if m:
            instructions[int(m.group(1), 16)] = normalize(m.group(2))
    map_re = re.compile(
        r"^([0-9a-f]+)-[0-9a-f]+ r-xp 00000000 \S+ \S+\s+\S*/"
        + re.escape(binary)
        + r"$"
    )
    bases = {
        int(m.group(1), 16)
        for line in maps.splitlines()
        if (m := map_re.match(line))
    }
    return md5, instructions, bases


def check_snippet(snippet, header, checkpoint, manifest, binary):
    """Raise Refused with the first mismatch between the snippet and the
    checkpoint."""
    name = f"{checkpoint.parent.name}/{checkpoint.name}"
    if header.get("binary") != binary:
        raise Refused(f"header binary {header.get('binary')!r} != {binary}")
    if name not in header["applies to"]:
        raise Refused(f"header does not list {name} under `applies to`")
    artifacts = manifest["artifacts"]
    for field, artifact in (("disk-image md5", "disk_image"),
                            ("kernel md5", "kernel")):
        if header.get(field) != artifacts[artifact]["md5"]:
            raise Refused(
                f"header {field} {header.get(field)} != manifest "
                f"{artifacts[artifact]['md5']}"
            )

    md5, instructions, bases = read_process_info(
        checkpoint / PROCESS_INFO_NAME, binary
    )
    if header.get("disassembly md5") != md5:
        raise Refused(
            f"header disassembly md5 {header.get('disassembly md5')} != {md5}"
        )

    offset = check_lines(snippet, instructions)
    if bases != {offset}:
        raise Refused(
            f"load base(s) {sorted(hex(b) for b in bases)} != offset {offset:#x}"
        )
    check_chains(snippet, offset)


def check_lines(snippet: str, instructions: dict) -> int:
    """The snippet's `offset`, once every instruction line names the
    instruction the disassembly has at its PC and every exit is a `ret` or
    an unconditional branch (tail call)."""
    offset = None
    for line in snippet.splitlines():
        code = line.split("//")[0].strip()
        if not code:
            continue
        if code.startswith("offset"):
            offset = int(code.split(":")[1], 16)
            continue
        if code.startswith("func"):
            continue
        if code.startswith("ret"):
            pc = int(code.split()[1], 16)
            text = instructions.get(pc)
            if text is None or not (text == "ret"
                                    or re.fullmatch(r"b [0-9a-f]+", text)):
                raise Refused(f"exit {pc:#x} is {text!r}, not a ret or tail call")
            continue
        left = code.split("label:")[0]
        pc_text, _, inst = left.partition(":")
        pc = int(pc_text, 16)
        tokens = inst.split()
        tokens[0] = tokens[0].split("@")[0]
        expected = normalize(" ".join(tokens))
        if instructions.get(pc) != expected:
            raise Refused(
                f"{pc:#x} is {instructions.get(pc)!r} in the disassembly, "
                f"snippet says {expected!r}"
            )
    if offset is None:
        raise Refused("snippet has no `offset`")
    return offset


def check_chains(snippet: str, offset: int) -> None:
    """Refuse chains InstructionQueue::addProducerConsumerChain would not
    accept, as register_snippet registers them. A labelled line on its own
    only labels its access (no chain)."""
    _, chains = process_snippet(snippet)
    roles, relations = {}, set()
    for chain in chains:
        pcs = [inst.pc() for inst in chain]
        where = f"chain starting at {pcs[0] - offset:#x}"
        if len(chain) == 1:
            if chain[0].label() == "n/a":
                raise Refused(f"{where} is one unlabelled instruction")
            continue
        if chain[0].label() == "n/a" or chain[-1].label() == "n/a":
            raise Refused(f"{where} is not labelled at both ends")
        relation = (f"{chain[-1].label()}[{chain[0].label()}]"
                    f"{chain[-1].label_version()}")
        if relation in relations:
            raise Refused(f"relation {relation} is defined twice")
        relations.add(relation)
        for i, pc in enumerate(pcs):
            role = ("producer" if i == 0 else
                    "consumer" if i == len(pcs) - 1 else "prosumer")
            if role == "consumer" and pc in roles:
                raise Refused(f"{pc - offset:#x} ends two chains or has two roles")
            if roles.setdefault(pc, role) != role:
                raise Refused(
                    f"{pc - offset:#x} is both {roles[pc]} and {role}"
                )


def check_se_snippet(path: Path) -> str:
    """Check an SE snippet against the binary its header names: the
    binary's md5, the instruction at every PC (objdump -d of the binary),
    the exits, the chains, and `offset` 0 (gem5 SE loads the executable,
    position-independent or not, at its link addresses; only the
    interpreter is relocated, Process::updateBias). Returns the binary."""
    snippet = path.read_text()
    header = read_header(snippet)
    binary = WORKLOADS_DIR / header.get("binary", "")
    if not header.get("binary") or not binary.is_file():
        raise Refused(f"header binary {header.get('binary')!r} is not a file")
    md5 = hashlib.md5(binary.read_bytes()).hexdigest()
    if header.get("binary md5") != md5:
        raise Refused(f"header binary md5 {header.get('binary md5')} != {md5}")
    disassembly = subprocess.run(
        [OBJDUMP, "-d", str(binary)], check=True, capture_output=True,
        text=True,
    ).stdout
    line_re = re.compile(r"^\s*([0-9a-f]+):\t[0-9a-f]{8} \t(.*)$")
    instructions = {
        int(m.group(1), 16): normalize(m.group(2))
        for line in disassembly.splitlines()
        if (m := line_re.match(line))
    }
    offset = check_lines(snippet, instructions)
    if offset != 0:
        raise Refused(f"offset {offset:#x} != 0 (gem5 SE does not relocate)")
    check_chains(snippet, offset)
    return header["binary"]


def check_se_snippets() -> int:
    counts, failed = {}, False
    for path in sorted(SE_SNIPPETS_DIR.glob("*.snippet")):
        try:
            status, detail = "ok", check_se_snippet(path)
        except Refused as error:
            status, detail = "refused", str(error)
        counts[status] = counts.get(status, 0) + 1
        failed |= status == "refused"
        print(f"{status:8s} se/{path.name}: {detail}")
    print(", ".join(f"{n} {s}" for s, n in sorted(counts.items())))
    return 1 if failed else 0


def process(checkpoint: Path, check_only: bool,
            snippets: Path = INSIGHTS_DIR) -> tuple:
    """(status, detail) for one checkpoint; status is written, same,
    differs, skipped or refused."""
    manifest = json.loads((checkpoint / MANIFEST_NAME).read_text())
    workload = manifest["workload"]
    if workload.get("variant") == "hov":
        return "skipped", "hov (no hov snippets yet)"
    binary = binary_name(workload)
    source = snippets / f"{binary}.snippet"
    if not source.exists():
        raise Refused(f"no snippet {source.name}")
    snippet = source.read_text()
    check_snippet(snippet, read_header(snippet), checkpoint, manifest, binary)

    target = checkpoint / SNIPPET_NAME
    if check_only:
        if target.exists() and target.read_text() == snippet:
            return "same", binary
        return "differs", f"{binary}: {SNIPPET_NAME} missing or different"
    target.write_text(snippet)
    return "written", binary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="compare instead of writing")
    parser.add_argument("--snippets", type=Path, default=INSIGHTS_DIR,
                        help="directory of <binary>.snippet files "
                        "(v2/ for the v2 images)")
    parser.add_argument("--se", action="store_true",
                        help="check the SE binaries' snippets (se/) "
                        "against the binaries instead")
    parser.add_argument("checkpoints", nargs="*", type=Path)
    args = parser.parse_args()
    if args.se:
        return check_se_snippets()

    checkpoints = [c.resolve() for c in args.checkpoints] or sorted(
        c for d in CHECKPOINT_DIRS if d.exists() for c in d.iterdir()
        if (c / MANIFEST_NAME).exists()
    )
    counts = {}
    failed = False
    for checkpoint in checkpoints:
        try:
            status, detail = process(checkpoint, args.check,
                                     args.snippets.resolve())
        except Refused as error:
            status, detail = "refused", str(error)
        counts[status] = counts.get(status, 0) + 1
        failed |= status in ("refused", "differs")
        print(f"{status:8s} {checkpoint.parent.name}/{checkpoint.name}: {detail}")
    print(", ".join(f"{n} {s}" for s, n in sorted(counts.items())))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
