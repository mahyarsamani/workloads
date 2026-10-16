import hashlib
import struct
import platform

from pathlib import Path
from typing import List, Optional, Tuple

from m5 import options
from m5.core import setInterpDir
from m5.objects import RedirectPath
from m5.util import fatal, inform


from gem5.components.boards.abstract_board import AbstractBoard

from gem5.resources.resource import BinaryResource
from gem5.resources.workload import WorkloadResource

from .workload_insights import read_header, register_snippet


_base_dir = Path(__file__).parent.absolute()
# The SE binaries' insights snippets, <binary dir>_<binary>.snippet, each
# checked by eval-artifacts/insights/generate_insights.py --se.
_se_snippets_dir = _base_dir / "eval-artifacts" / "insights" / "se"


class SEExitHandler:
    """The exit events of an SE run whose binary marks its region of
    interest, and optionally a warm-up before it, with work begin/end
    pairs (workloads/annotate: roi_begin_/roi_end_ in the gem5se flavour).
    The pairs are told apart by their order: with a warm-up the first pair
    is the warm-up and the second the ROI; without one the first pair is
    the ROI.

    Phases of the run script's switchable processor: the setup phase runs
    from the start to the first marker; the warm-up phase (if any) runs the
    warm-up iteration and up to the ROI marker; at the ROI marker the stats
    are reset and the main phase (O3) takes over. The ROI ends at its work
    end, or after `measure` of simulated time if given; either way the
    stats are dumped and the run stops. With `sample_period`, the stats are
    also dumped every `sample_period` of simulated time inside the ROI,
    without a reset (each dump covers the ROI so far, as the full-system
    restores sample), so a long run yields data before it ends.
    window.json in the output directory records the ticks, the number of
    samples, and how the run ended (`roi_end` or `measure`)."""

    def __init__(
        self,
        has_warmup: bool,
        warmup_phase: Optional[str],
        main_phase: str,
        measure: Optional[str] = None,
        sample_period: Optional[str] = None,
    ):
        self._has_warmup = has_warmup
        self._warmup_phase = warmup_phase
        self._main_phase = main_phase
        self._measure = measure
        self._sample_period = sample_period
        self._info = {
            "has_warmup": has_warmup,
            "warmup_phase": warmup_phase,
            "measure": measure,
            "sample_period": sample_period,
            "samples": 0,
        }

    def _record(self, **fields) -> None:
        import json

        from m5 import curTick

        from .fs_workload_wrapper import get_outdir

        self._info.update(fields)
        self._info["tick"] = curTick()
        with open(Path(get_outdir()) / "window.json", "w") as f:
            json.dump(self._info, f, indent=2)

    def get_exit_event_handler(self, board: AbstractBoard) -> dict:
        from m5 import curTick
        from m5.stats import reset as reset_stats
        from m5.ticks import fromSeconds
        from m5.util import fatal
        from m5.util.convert import toLatency

        from gem5.simulate.exit_event import ExitEvent
        from gem5.simulate.exit_event_generators import SimStep

        from .fs_workload_wrapper import dump_stats

        processor = board.get_processor()
        # NOTE: The pair that is the ROI: the second with a warm-up.
        roi_pair = 2 if self._has_warmup else 1
        state = {"begins": 0, "ends": 0, "measure_end": None}

        def next_step():
            """Simulate to the next sample or the end of `measure`,
            whichever comes first, as a time string SimStep converts."""
            steps = []
            if self._sample_period is not None:
                steps.append(fromSeconds(toLatency(self._sample_period)))
            if state["measure_end"] is not None:
                steps.append(state["measure_end"] - curTick())
            if not steps:
                return SimStep.REMAINING_TIME
            return f"{max(min(steps), 1) / fromSeconds(1.0)}s"

        def handle_work_begin(board):
            while True:
                state["begins"] += 1
                if state["begins"] < roi_pair:
                    if self._warmup_phase is not None:
                        processor.switch(self._warmup_phase)
                    self._record(stage="warmup", warmup_start=curTick())
                    inform(f"Warm-up began on phase {processor.current_phase()}.")
                    yield SimStep.REMAINING_TIME
                elif state["begins"] == roi_pair:
                    reset_stats()
                    processor.switch(self._main_phase)
                    self._record(stage="roi", roi_start=curTick())
                    if self._measure is not None:
                        state["measure_end"] = curTick() + fromSeconds(
                            toLatency(self._measure)
                        )
                    inform(
                        f"ROI began: reset stats, switched to phase "
                        f"{self._main_phase}."
                    )
                    yield next_step()
                else:
                    fatal(f"Unexpected work begin #{state['begins']}.")

        def handle_work_end(board):
            while True:
                state["ends"] += 1
                if state["ends"] < roi_pair:
                    self._record(stage="warmup_done", warmup_end=curTick())
                    inform("Warm-up ended.")
                    yield SimStep.REMAINING_TIME
                else:
                    dump_stats()
                    self._record(stage="done", ended_by="roi_end")
                    inform("ROI ended: dumped stats.")
                    yield SimStep.STOP

        def handle_max_tick(board):
            while True:
                if state["begins"] < roi_pair:
                    fatal("Reached a max tick before the ROI began.")
                dump_stats()
                if (
                    state["measure_end"] is not None
                    and curTick() >= state["measure_end"]
                ):
                    self._record(stage="done", ended_by="measure")
                    inform(
                        f"Measured {self._measure} of the ROI: dumped stats."
                    )
                    yield SimStep.STOP
                else:
                    self._record(samples=self._info["samples"] + 1)
                    inform(
                        f"Sample {self._info['samples']} of the ROI: dumped "
                        "stats."
                    )
                    yield next_step()

        def handle_exit(board):
            while True:
                if state["ends"] < roi_pair:
                    fatal(
                        "The workload exited before the end of its ROI; "
                        "see simout.txt and simerr.txt."
                    )
                yield SimStep.STOP

        return {
            ExitEvent.WORKBEGIN: handle_work_begin(board),
            ExitEvent.WORKEND: handle_work_end(board),
            ExitEvent.MAX_TICK: handle_max_tick(board),
            ExitEvent.EXIT: handle_exit(board),
        }


class SEWorkloadWrapper:
    """A single-threaded SE binary. Subclasses that run several threads
    override `setup` and `_env_list`; a run script calls `setup` with its
    core count before building the board, then `get_workload`.

    `marks_roi`: the binary marks its region of interest with a work
    begin/end pair, so the run script runs it in phases with SEExitHandler
    (otherwise on its main cores from the start, with gem5's default exit
    handling, as the hov unit and kernel tests expect); `has_warmup`: it
    also marks a warm-up iteration with a pair before the ROI's;
    `warmup_cpu`: the CPU of that warm-up iteration ("timing", or "none"
    to stay on the atomic setup cores, which leave the caches cold);
    `mem_size`: the board's memory. Both are the run script's defaults
    when it is not given others."""

    def __init__(
        self,
        binary_path: Path,
        arguments: List,
        marks_roi: bool = False,
        has_warmup: bool = False,
        warmup_cpu: str = "timing",
        mem_size: str = "16GiB",
    ):
        assert marks_roi or not has_warmup
        assert warmup_cpu in ("timing", "none")
        self._binary_path = binary_path
        self._arguments = arguments
        self._marks_roi = marks_roi
        self._has_warmup = has_warmup
        self._warmup_cpu = warmup_cpu
        self._mem_size = mem_size
        self._hov_entries = {}

    def insights_snippet(self) -> Optional[str]:
        """The insights snippet of this binary, or None: the snippet
        <binary dir>_<binary>.snippet whose header names this binary (the
        hov binaries have none). A snippet whose `binary md5` differs from
        the binary's is stale (its PCs name other instructions) and fatal:
        gem5 would silently label nothing."""
        binary = self._binary_path
        path = _se_snippets_dir / f"{binary.parent.name}_{binary.name}.snippet"
        if not path.exists():
            return None
        snippet = path.read_text()
        header = read_header(snippet)
        if header.get("binary") != str(binary.relative_to(_base_dir)):
            return None
        md5 = hashlib.md5(binary.read_bytes()).hexdigest()
        if header.get("binary md5") != md5:
            fatal(
                f"{path.name} is for another build of {binary} (md5 "
                f"{header.get('binary md5')}, the binary's is {md5}): "
                "re-derive it and check it with generate_insights.py --se."
            )
        return snippet

    def hov_entries(self) -> dict:
        """The side-car entries the hov binary binds, as {entry number:
        {"index": index array, "data": data array}}, named as the ref
        snippet labels the arrays; {} for a ref binary."""
        return self._hov_entries

    def add_workload_insights(self, board: AbstractBoard) -> None:
        """Register the binary's insights snippet and the hov entries' names
        with the board's processor, whose O3 cores (the novo cores of the
        region of interest) label accesses with them; other cores ignore
        them."""
        processor = board.get_processor()
        snippet = self.insights_snippet()
        if snippet is not None:
            register_snippet(processor, snippet)
            inform(f"Registered the insights snippet of {self._binary_path}.")
        for pair, arrays in self.hov_entries().items():
            processor.add_hov_entry_names(
                pair, arrays["index"], arrays["data"]
            )

    def marks_roi(self) -> bool:
        return self._marks_roi

    def has_warmup(self) -> bool:
        return self._has_warmup

    def warmup_cpu(self) -> str:
        return self._warmup_cpu

    def mem_size(self) -> str:
        return self._mem_size

    def setup(self, num_cores: int, threads: Optional[int] = None) -> int:
        """Fix the thread count for a board of `num_cores` cores (`threads`
        overrides the workload's own) and return how many spare cores the
        board must add beyond `num_cores`."""
        if threads not in (None, 1):
            raise ValueError(f"{self._binary_path.name} is single-threaded.")
        return 0

    def _env_list(self) -> List[str]:
        """The binary's environment, as "NAME=value" strings."""
        return []

    def get_workload(self):
        parameters = {
            "binary": BinaryResource(str(self._binary_path)),
            "arguments": [str(arg) for arg in self._arguments],
        }
        env_list = self._env_list()
        if env_list:
            parameters["env_list"] = env_list
        return WorkloadResource(
            function="set_se_binary_workload",
            parameters=parameters,
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

        # NOTE: A dynamic binary always loads its libraries from the
        # sysroot it was built against, even on a host of its own
        # architecture, so every host runs the same libraries.
        if not self._dynamically_linked():
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


class OpenMPWorkloadWrapper(SEWorkloadWrapper):
    """An OpenMP SE binary running `threads` threads, one per core (None:
    one per core of the board).

    SE mode has no scheduler: the process starts on core 0 and every clone
    takes the first halted core (System::Threads::findFree), so a thread
    the runtime starts beyond `threads` (e.g. a monitor thread) needs a
    free core or the clone fails. `setup` therefore asks for one spare
    core when the threads fill the board, and none otherwise."""

    def __init__(
        self,
        binary_path: Path,
        arguments: List,
        threads: Optional[int] = None,
        marks_roi: bool = True,
        has_warmup: bool = False,
        warmup_cpu: str = "timing",
        mem_size: str = "16GiB",
    ):
        super().__init__(
            binary_path, arguments, marks_roi, has_warmup, warmup_cpu,
            mem_size,
        )
        self._threads = threads
        self._num_threads = None

    def setup(self, num_cores: int, threads: Optional[int] = None) -> int:
        num_threads = threads or self._threads or num_cores
        if not 0 < num_threads <= num_cores:
            raise ValueError(
                f"{num_threads} threads do not fit {num_cores} cores."
            )
        self._num_threads = num_threads
        return 1 if num_threads == num_cores else 0

    def _env_list(self) -> List[str]:
        # NOTE: Idle threads block in futex instead of spinning, so a
        # waiting thread commits no instructions.
        assert self._num_threads is not None, "setup() was not called."
        return [
            f"OMP_NUM_THREADS={self._num_threads}",
            "OMP_WAIT_POLICY=passive",
            "GOMP_SPINCOUNT=0",
        ]


_hov_test_dir = _base_dir / "hov" / "tests"


class HOVUnitTestWrapper(SEWorkloadWrapper):
    def __init__(self, name: str, arguments: list):
        super().__init__(_hov_test_dir / "unit" / name / name, arguments)


test_load = HOVUnitTestWrapper("test_load", [])
test_store = HOVUnitTestWrapper("test_store", [])
test_forward = HOVUnitTestWrapper("test_forward", [])
test_load_idx = HOVUnitTestWrapper("test_load_idx", [])


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


# OpenMP kernels built by scripts/build-se-kernels.sh, whose region of
# interest is marked with gem5 work begin/end: variant "ref" (flavour
# gem5se) or "hov" (flavour gem5se-hov: the region of interest issues
# ldind, the warm-up runs the ref code).
_se_bin_dirs = {
    "ref": _base_dir / "se-bin" / "gem5se",
    "hov": _base_dir / "se-bin" / "gem5se-hov",
}
_se_bin_dir = _se_bin_dirs["ref"]


class GapbsWrapper(OpenMPWorkloadWrapper):
    """A gapbs kernel (pr, pr_spmv, bfs) on `graph_args` (e.g. ["-u", 20]
    for a generated uniform graph, ["-f", path] for a serialized one). PR
    and pr_spmv mark their first two iterations as the warm-up and the
    region of interest (one trial); BFS marks its first two trials (two
    trials, from different sources) and has no hov variant."""

    def __init__(
        self,
        kernel: str,
        graph_args: List,
        threads=None,
        variant="ref",
        **options,
    ):
        trials = 2 if kernel == "bfs" else 1
        super().__init__(
            _se_bin_dirs[variant] / "gapbs" / kernel,
            graph_args + ["-n", trials],
            threads,
            has_warmup=True,
            **options,
        )
        if variant == "hov":
            # HOV_ENTRY_CONTRIB in pr.cc and pr_spmv.cc.
            self._hov_entries = {
                0: {"index": "in_neighbors", "data": "outgoing_contrib"}
            }


class NPBCGWrapper(OpenMPWorkloadWrapper):
    """NPB-CPP's OpenMP CG of class `npb_class`; the untimed initial
    iteration is the warm-up and the first timed iteration the region of
    interest."""

    def __init__(
        self, npb_class: str, threads=None, variant="ref", **options
    ):
        super().__init__(
            _se_bin_dirs[variant] / "npb" / f"cg.{npb_class}",
            [],
            threads,
            has_warmup=True,
            **options,
        )
        if variant == "hov":
            # HOV_ENTRY_P and HOV_ENTRY_Z in cg.cpp.
            self._hov_entries = {
                0: {"index": "colidx", "data": "p"},
                1: {"index": "colidx", "data": "z"},
            }


class UMEKernelWrapper(OpenMPWorkloadWrapper):
    """A UME-kernels kernel (DX100's standalone UME gradients, SIFT build)
    on `corners` corners with random index maps from `seed`: each corner's
    zone and point are its own index plus a uniform offset within
    `window` (None: DX100's 85,000), so the active working set of each
    gathered array spans about 2 * window elements. Its first pass is the
    warm-up and its second the region of interest."""

    def __init__(
        self,
        kernel: str,
        corners: int,
        seed: int = 1,
        window: Optional[int] = None,
        threads=None,
        variant="ref",
        **options,
    ):
        args = [corners, seed] + ([] if window is None else [window])
        super().__init__(
            _se_bin_dirs[variant] / "ume" / kernel,
            args,
            threads,
            has_warmup=True,
            **options,
        )
        if variant == "hov" and kernel == "gradzatz":
            # HOV_ENTRY_ZONE_VOLUME and HOV_ENTRY_POINT_GRADIENT in
            # gradzatz.cpp.
            self._hov_entries = {
                0: {"index": "c_to_z_map", "data": "zone_volume_exp"},
                1: {"index": "c_to_p_map", "data": "point_gradient"},
            }
        elif variant == "hov" and kernel == "gradzatz_invert":
            # HOV_ENTRY_CORNER_VOLUME and HOV_ENTRY_POINT_GRADIENT in
            # gradzatz_invert.cpp (the second is read at the corner the
            # first returns).
            self._hov_entries = {
                0: {"index": "z_to_c_indices", "data": "corner_volume"},
                1: {"index": "c_to_p_map", "data": "point_gradient"},
            }
        elif variant == "hov" and kernel == "gradzatp_invert":
            # HOV_ENTRY_CORNER_VOLUME, HOV_ENTRY_CSURF and
            # HOV_ENTRY_ZONE_FIELD in gradzatp_invert.cpp (the third is
            # read at the corner the first returns).
            self._hov_entries = {
                0: {"index": "p_to_c_indices", "data": "corner_volume"},
                1: {"index": "p_to_c_indices", "data": "csurf"},
                2: {"index": "c_to_z_map", "data": "zone_field"},
            }
        elif variant == "hov" and kernel == "gradzatp":
            # HOV_ENTRY_ZONE_FIELD in gradzatp.cpp (its scatter-adds stay
            # atomics).
            self._hov_entries = {
                0: {"index": "c_to_z_map", "data": "zone_field"},
            }


class SpMVWrapper(OpenMPWorkloadWrapper):
    """The CSR SpMV (workloads/spmv) on `matrix_args`, e.g. ["stencil27",
    64], ["uniform", 1 << 20, 16], ["mtx", path] or ["csr", path]
    (mtx2csr's binary CSR, loaded without parsing); one product is the
    warm-up and the next the region of interest."""

    def __init__(
        self, matrix_args: List, threads=None, variant="ref", **options
    ):
        super().__init__(
            _se_bin_dirs[variant] / "spmv" / "spmv",
            matrix_args,
            threads,
            has_warmup=True,
            **options,
        )
        if variant == "hov":
            # HOV_ENTRY_X in spmv.cpp.
            self._hov_entries = {0: {"index": "col", "data": "x"}}


# Small inputs, for smoke tests.
gapbs_pr_u14 = GapbsWrapper("pr", ["-u", 14])
gapbs_pr_spmv_u14 = GapbsWrapper("pr_spmv", ["-u", 14])
gapbs_bfs_u14 = GapbsWrapper("bfs", ["-u", 14])
npb_cg_S = NPBCGWrapper("S")
npb_cg_B = NPBCGWrapper("B")
ume_gradzatz_300k = UMEKernelWrapper("gradzatz", 300000)
ume_gradzatz_invert_300k = UMEKernelWrapper("gradzatz_invert", 300000)
ume_gradzatp_invert_300k = UMEKernelWrapper("gradzatp_invert", 300000)
ume_gradzatp_300k = UMEKernelWrapper("gradzatp", 300000)
spmv_stencil27_32 = SpMVWrapper(["stencil27", 32])
spmv_uniform_64k = SpMVWrapper(["uniform", 1 << 16, 16])

# The evaluation inputs, sized so that the indirectly accessed array is
# about the system cache's 32 MiB (and twice that), by name. Graphs come
# from scripts/make-se-inputs.sh (se-inputs/graphs, git-ignored), matrices
# from scripts/make-se-matrices.sh (se-inputs/matrices, git-ignored).
_graphs_dir = _base_dir / "se-inputs" / "graphs"
_matrices_dir = _base_dir / "se-inputs" / "matrices"


def _evaluation_workloads() -> dict:
    """Every evaluation input in its ref variant (`<name>`) and, for the
    kernels with one, its hov variant (`<name>_hov`). Every run goes to
    completion: the warm-up iteration, then the region of interest.

    An input whose gathered data are smaller than 4 MiB runs its warm-up
    on the atomic setup cores (`cold`), leaving the caches cold for both
    variants: on TimingSimpleCPU the ref warm-up would leave the whole
    data set in the private caches, which the ref region of interest then
    hits and SIFT, whose region gathers through the Gather and Value
    Units, cannot (author, 2026-10-13)."""
    workloads = {}
    cold = {"warmup_cpu": "none"}

    def add(name, wrapper_cls, *args, hov=True, **kwargs):
        workloads[name] = wrapper_cls(*args, **kwargs)
        if hov:
            workloads[f"{name}_hov"] = wrapper_cls(
                *args, variant="hov", **kwargs
            )

    # gapbs PageRank, Jacobi (pr_spmv) and Gauss-Seidel (pr): contrib is
    # 4 B per node, so scale 20 is 4 MiB and scale 22 16 MiB (past the
    # 1 MiB L2s, within the 32 MiB system cache; hours per run), scale 23
    # 32 MiB, scale 24 64 MiB and scale 27 512 MiB (a ~16 GB graph, hence
    # 64 GiB of memory; days). BFS is out (frontier bitmap and
    # compare-and-swap, no hov variant; a custom BFS later).
    for kernel in ["pr_spmv", "pr"]:
        for kind in ["uniform", "kron"]:
            for scale in [20, 22, 23, 24, 27]:
                graph = _graphs_dir / f"{kind}-{scale}.sg"
                big = {"mem_size": "64GiB"} if scale == 27 else {}
                add(
                    f"gapbs_{kernel}_{kind}{scale}",
                    GapbsWrapper,
                    kernel,
                    ["-f", graph],
                    **big,
                )
    # NPB CG as the standard benchmark: x is 1.2 MB (C, cold) and 12 MB (D),
    # below the system cache (no class reaches it: E allocates ~78 GB).
    add("npb_cg_C", NPBCGWrapper, "C", **cold)
    add("npb_cg_D", NPBCGWrapper, "D")
    # SpMV: x is 8 B per row; 2^22 rows (32 MiB), 2^23 (64 MiB) and 2^26
    # (512 MiB; ~12 GB of matrix) uniform with 16 per row. The stencil
    # control is out (CBU 100% by construction). Two SuiteSparse matrices,
    # binary CSR from scripts/make-se-matrices.sh: soc-LiveJournal1 (4.8M
    # rows, 69M nonzeros, power-law; x 37 MiB) and Queen_4147 (3D finite
    # elements, 4.1M rows, 329M nonzeros; x 32 MiB, ~4 GB of matrix).
    for name, matrix in [
        ("livejournal", "soc-LiveJournal1"),
        ("queen4147", "Queen_4147"),
    ]:
        add(
            f"spmv_{name}",
            SpMVWrapper,
            ["csr", _matrices_dir / f"{matrix}.csr"],
        )
    # 2^20 rows (x 8 MiB): past the 1 MiB L2s, a few hours per run.
    add("spmv_uniform_1m", SpMVWrapper, ["uniform", 1 << 20, 16])
    add("spmv_uniform_4m", SpMVWrapper, ["uniform", 1 << 22, 16])
    add("spmv_uniform_8m", SpMVWrapper, ["uniform", 1 << 23, 16])
    add(
        "spmv_uniform_64m",
        SpMVWrapper,
        ["uniform", 1 << 26, 16],
        mem_size="32GiB",
    )
    # UME gradzatz: DX100's setting (2M corners, window 85,000: a ~680 KB
    # working set, cold) and windows of 2^22, 2^23 and 2^27 elements, whose
    # active working sets span 2 * window floats: 32, 64 and 512 MiB.
    add("ume_gradzatz_dx100", UMEKernelWrapper, "gradzatz", 2_000_000, **cold)
    # DX100's setting with 8x its distance (window 680,000): the active
    # working set of each gathered float array is about 5.4 MB, past the
    # L2s and within the system cache (warm-up on TimingSimpleCPU).
    add(
        "ume_gradzatz_dx100_w8",
        UMEKernelWrapper,
        "gradzatz",
        2_000_000,
        window=8 * 85_000,
    )
    for name, size in [("32m", 1 << 22), ("64m", 1 << 23), ("512m", 1 << 27)]:
        add(
            f"ume_gradzatz_{name}",
            UMEKernelWrapper,
            "gradzatz",
            size,
            window=size,
        )
    # UME gradzatz_invert and gradzatp_invert: gradzatz's corner counts and
    # windows, looped over zones (points) through a CSR map of their
    # corners. A zone's (point's) corners lie within 2 * window of it, so
    # the corner arrays gathered through the CSR indices span 2 * window
    # floats (at most the n corners: 16 and 32 MiB at 2^22 and 2^23), and
    # the point (zone) array gathered at those corners 4 * window floats
    # (at most n + 2 * window). No 512m input: at 2^27 corners their
    # arrays (116 to 132 B per corner, 15.6 to 17.7 GB, more during the
    # CSR setup) reach or exceed the 16 GiB board. gradzatp is
    # gradzatz's mirror (corners to points), with the same inputs; only its
    # zone_field gather offloads (its scatter-adds stay atomics), and its
    # 512m input is left out with the others'.
    for kernel in ["gradzatz_invert", "gradzatp_invert", "gradzatp"]:
        add(f"ume_{kernel}_dx100", UMEKernelWrapper, kernel, 2_000_000, **cold)
        add(
            f"ume_{kernel}_dx100_w8",
            UMEKernelWrapper,
            kernel,
            2_000_000,
            window=8 * 85_000,
        )
        for name, size in [("32m", 1 << 22), ("64m", 1 << 23)]:
            add(
                f"ume_{kernel}_{name}",
                UMEKernelWrapper,
                kernel,
                size,
                window=size,
            )
    # Probe input, for quick looks past the L2: x (8 MiB) overflows the
    # 1 MiB L2s, not the 32 MiB system cache (PR's is gapbs_pr_uniform20).
    add("probe_spmv_uniform_1m", SpMVWrapper, ["uniform", 1 << 20, 16])
    add(
        "probe_pr_uniform20",
        GapbsWrapper,
        "pr",
        ["-f", _graphs_dir / "uniform-20.sg"],
    )
    # Small inputs of every kernel, for functional checks (all cold).
    add("smoke_pr_u16", GapbsWrapper, "pr", ["-u", 16], **cold)
    add("smoke_pr_spmv_u16", GapbsWrapper, "pr_spmv", ["-u", 16], **cold)
    add("smoke_cg_S", NPBCGWrapper, "S", **cold)
    add(
        "smoke_spmv_uniform_64k",
        SpMVWrapper,
        ["uniform", 1 << 16, 16],
        **cold,
    )
    add(
        "smoke_ume_gradzatz_300k",
        UMEKernelWrapper,
        "gradzatz",
        300000,
        **cold,
    )
    for kernel in ["gradzatz_invert", "gradzatp_invert", "gradzatp"]:
        add(
            f"smoke_ume_{kernel}_300k",
            UMEKernelWrapper,
            kernel,
            300000,
            **cold,
        )
    return workloads


SE_EVALUATION_WORKLOADS = _evaluation_workloads()

# se-tests/share_inval: two threads share 32 KiB (CBU of invalidated blocks).
share_inval = OpenMPWorkloadWrapper(
    _se_bin_dir / "se-tests" / "share_inval", [], threads=2
)

# se-tests/share_false: two threads write disjoint halves of every line of
# 32 KiB (false sharing only, for the snoop-sharing counters).
share_false = OpenMPWorkloadWrapper(
    _se_bin_dir / "se-tests" / "share_false", [], threads=2
)
