import struct
import platform

from pathlib import Path
from typing import List, Optional, Tuple

from m5 import options
from m5.core import setInterpDir
from m5.objects import RedirectPath
from m5.util import inform


from gem5.components.boards.abstract_board import AbstractBoard

from gem5.resources.resource import BinaryResource
from gem5.resources.workload import WorkloadResource


_base_dir = Path(__file__).parent.absolute()


class SEWorkloadWrapper:
    def __init__(self, binary_path: Path, arguments: List):
        self._binary_path = binary_path
        self._arguments = arguments

    def get_workload(self):
        return WorkloadResource(
            function="set_se_binary_workload",
            parameters={
                "binary": BinaryResource(str(self._binary_path)),
                "arguments": [str(arg) for arg in self._arguments],
            },
        )

    def _dynamically_linked(self):
        with open(self._binary_path, "rb") as binary:
            if binary.read(4) != b"\x7fELF":
                raise ValueError(f"{self._binary_path} is not an ELF binary")

            binary.seek(4)
            ei_class = binary.read(1)
            is_64 = ei_class == b"\x02"

            binary.seek(0x20 if is_64 else 0x1C)
            e_phoff = struct.unpack(
                "<Q" if is_64 else "<I", binary.read(8 if is_64 else 4)
            )[0]

            binary.seek(0x36 if is_64 else 0x2A)
            e_phentsize = struct.unpack("<H", binary.read(2))[0]
            e_phnum = struct.unpack("<H", binary.read(2))[0]

            for i in range(e_phnum):
                binary.seek(e_phoff + i * e_phentsize)
                p_type = struct.unpack("<I", binary.read(4))[0]
                if p_type == 3:
                    return True
            return False

    def _get_architecture(self):
        with open(self._binary_path, "rb") as binary:
            if binary.read(4) != b"\x7fELF":
                raise ValueError(f"{self._binary_path} is not an ELF binary")

            binary.seek(18)
            e_machine = struct.unpack("<H", binary.read(2))[0]

        # ELF e_machine mapping
        elf_arch_map = {
            0x03: "x86",
            0x3E: "x86_64",
            0x28: "arm",
            0xB7: "aarch64",
            0xF3: "riscv",
            0x08: "mips",
        }

        return elf_arch_map.get(e_machine, f"unknown({e_machine})")

    def _compatible_with_host(self):
        binary_arch = self._get_architecture()
        host_arch = platform.machine().lower()

        normalize = {
            "amd64": "x86_64",
            "x64": "x86_64",
            "i386": "x86",
            "i686": "x86",
            "armv7l": "arm",
            "arm64": "aarch64",
        }

        binary_arch = normalize.get(binary_arch, binary_arch)
        host_arch = normalize.get(host_arch, host_arch)

        return binary_arch == host_arch

    def setup_linking(
        self,
        board: AbstractBoard,
        sysroot_base: Path,
        extra_libs: Optional[List[Tuple[Path, str]]] = None,
    ):
        """Set up dynamic linking for cross-compiled SE-mode binaries.

        Args:
            board: The board to configure redirect paths on.
            sysroot_base: Base directory containing per-arch sysroots.
            extra_libs: Optional list of (host_path, app_path) tuples.
                Each host_path is a directory containing shared libraries,
                and app_path is the guest path it should be reachable from
                (e.g. "/lib" or "/usr/lib").
        """
        inform(f"binary at {self._binary_path}:")
        inform(f"dynamically linked: {self._dynamically_linked()}")
        inform(f"compatible with host: {self._compatible_with_host()}")

        if not self._dynamically_linked() or self._compatible_with_host():
            return

        sysroot_path = sysroot_base / self._get_architecture()
        outdir = Path(options.outdir)

        proc = outdir / "fs_emulation" / "proc"
        sys = outdir / "fs_emulation" / "sys"
        tmp = outdir / "fs_emulation" / "tmp"
        proc.mkdir(parents=True, exist_ok=True)
        sys.mkdir(parents=True, exist_ok=True)
        tmp.mkdir(parents=True, exist_ok=True)

        setInterpDir(str(sysroot_path))

        # Base library search paths from sysroot
        lib_redirects = {
            "/lib": [str(sysroot_path / "lib")],
            "/lib64": [str(sysroot_path / "lib")],
            "/usr/lib": [str(sysroot_path / "usr/lib")],
            "/usr/lib64": [str(sysroot_path / "usr/lib")],
        }

        # Merge caller-provided extra library directories
        for host_path, app_path in extra_libs or []:
            lib_redirects.setdefault(app_path, []).append(str(host_path))

        board.redirect_paths = [
            RedirectPath(app_path="/proc", host_paths=[str(proc)]),
            RedirectPath(app_path="/sys", host_paths=[str(sys)]),
            RedirectPath(app_path="/tmp", host_paths=[str(tmp)]),
        ] + [
            RedirectPath(app_path=app_path, host_paths=host_paths)
            for app_path, host_paths in lib_redirects.items()
        ]


_hov_test_dir = _base_dir / "hov" / "tests"


class HOVUnitTestWrapper(SEWorkloadWrapper):
    def __init__(self, name: str, arguments: list):
        super().__init__(_hov_test_dir / "unit" / name / name, arguments)


test_load = HOVUnitTestWrapper("test_load", [])
test_store = HOVUnitTestWrapper("test_store", [])


class HOVKernelTestWrapper(SEWorkloadWrapper):
    def __init__(self, name: str, opt: str, arguments: list):
        super().__init__(
            _hov_test_dir / "kernel" / name / f"{name}{opt}", arguments
        )


class DotIndirect(HOVKernelTestWrapper):
    def __init__(self, opt: str):
        super().__init__(
            "dot_indirect",
            opt,
            [
                _hov_test_dir / "kernel" / "dot_indirect" / "index_a.txt",
                _hov_test_dir / "kernel" / "dot_indirect" / "index_b.txt",
                _hov_test_dir / "kernel" / "dot_indirect" / "data_a.txt",
                _hov_test_dir / "kernel" / "dot_indirect" / "data_b.txt",
            ],
        )


dot_indirect = DotIndirect("")
dot_indirect_sve = DotIndirect("_sve")
dot_indirect_hov = DotIndirect("_hov")


class ReduceIndirect(HOVKernelTestWrapper):
    def __init__(self, opt: str):
        super().__init__(
            "reduce_indirect",
            opt,
            [
                _hov_test_dir / "kernel" / "reduce_indirect" / "index.txt",
                _hov_test_dir / "kernel" / "reduce_indirect" / "data.txt",
            ],
        )


reduce_indirect = ReduceIndirect("")
reduce_indirect_sve = ReduceIndirect("_sve")
reduce_indirect_hov = ReduceIndirect("_hov")
