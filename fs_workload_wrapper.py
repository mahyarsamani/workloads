from types import SimpleNamespace
from .checkpoint_manifest import (
    MANIFEST_NAME,
    SNIPPET_NAME,
    artifact_path,
    read_manifest,
    write_manifest,
)
from .workload_insights import process_snippet

import argparse
import os
import re
import shutil

from enum import Enum


class WorkloadVariant(Enum):
    REF = "ref"
    HOV = "hov"


# The disk image each variant boots, relative to the SIFT project root (the
# run scripts' working directory). build-arm.sh builds them:
# `./build-arm.sh 22.04 <variant>` writes disk-images/arm-sift-<variant>-2204.
# A restore does not use these: it takes the image from the checkpoint's
# manifest (FSWorkloadWrapper.checkpoint_artifact_path).
DISK_IMAGES = {
    WorkloadVariant.REF: "workloads/disk-images/arm-sift-ref-2204/disk-image",
    WorkloadVariant.HOV: "workloads/disk-images/arm-sift-hov-2204/disk-image",
}


from pathlib import Path
from typing import Optional, Union

from m5 import options as m5_options
from m5.simulate import checkpoint
from m5.stats import reset as reset_stats
from m5.stats import dump as m5_dump_stats
from m5.util import inform, warn

from gem5.components.boards.abstract_board import AbstractBoard

from gem5.components.processors.multi_fidelity_processor import (
    MultiFidelityProcessor as SwitchableProcessor,
)
from gem5.simulate.exit_event import ExitEvent
from gem5.simulate.exit_event_generators import SimStep


_mpirun_command_template = (
    "mpirun -np {num_processes} "
    "{extra_args}"
    "-mca coll basic,self,libnbc -mca btl self,vader --noprefix {workload_cmd}"
)

_hov_syscalls_lib = "/home/gem5/workloads/hov/lib/libhov_syscalls.so"


def get_outdir():
    return Path(m5_options.outdir)


def copy_file(file_name: str, src_dir: Path, dst_dir: Path):
    src_path = src_dir / file_name
    dst_path = dst_dir / file_name
    if src_path.exists():
        dst_path.write_text(src_path.read_text())


def take_checkpoint(checkpoint_path: Path):
    inform(f"Taking a checkpoint in {checkpoint_path}.")
    checkpoint(str(checkpoint_path))


def dump_stats():
    outdir = get_outdir()
    stats_file = outdir / "stats.txt"

    try:
        old_size = os.path.getsize(stats_file)
    except OSError:
        old_size = 0

    m5_dump_stats()

    new_data = None
    with open(f"{outdir}/stats.txt", "rb") as stats_file:
        stats_file.seek(old_size)
        new_data = stats_file.read()

    if new_data:
        dump_name_pattern = re.compile(r"^stats_dump_(\d+)\.txt$")
        all_dumps = [
            f for f in outdir.iterdir() if dump_name_pattern.fullmatch(f.name)
        ]
        if all_dumps:
            dump_version = (
                max([int(f.stem.split("_")[-1]) for f in all_dumps]) + 1
            )
        else:
            dump_version = 0
        with open(
            outdir / f"stats_dump_{dump_version}.txt", "wb"
        ) as dump_file:
            dump_file.write(new_data)


def try_convert_bool(bool_like):
    def convert_str_bool(bool_like):
        assert bool_like.lower() in ["true", "false"]
        return True if bool_like.lower() == "true" else False

    def is_int_like(int_like):
        try:
            ret = int(int_like)
            return True
        except:
            return False

    def convert_int_bool(bool_like):
        assert bool_like >= 0
        return bool_like > 0

    if isinstance(bool_like, str):
        if is_int_like(bool_like):
            return convert_int_bool(bool_like)
        else:
            return convert_str_bool(bool_like)
    elif isinstance(bool_like, int):
        return convert_int_bool(bool_like)
    elif isinstance(bool_like, bool):
        return bool_like
    else:
        raise ValueError(
            "bool_like argument should be a "
            "string/positive integer/boolean."
        )


class ExitEventHandlerWrapper:
    def __init__(
        self,
        sample_stats: bool,
        sample_period: str,
        take_checkpoint: bool,
        checkpoint_path: Union[Path, None],
        has_warmup: bool,
    ):
        self._sample_stats = sample_stats
        self._sample_period = sample_period
        # Whether the ROI has begun. A restored checkpoint sets it from its
        # manifest (set_state).
        self._reacted_yet = False
        self._take_checkpoint = take_checkpoint
        self._checkpoint_path = checkpoint_path
        self._has_warmup = has_warmup
        # Called with the checkpoint path and the board after each
        # checkpoint; set by the workload wrapper to write the manifest.
        self._on_checkpoint = None

    def get_state(self) -> dict:
        """The handler's state, recorded in the manifest of a checkpoint so
        that restoring it continues from the same state."""
        return {"reacted_yet": self._reacted_yet}

    def set_state(self, state: dict) -> None:
        """Continue from `state` (from get_state at checkpoint time)."""
        self._reacted_yet = state["reacted_yet"]

    def _after_checkpoint(self, board: AbstractBoard):
        """Store everything that belongs with a checkpoint next to it:
        process_info.txt (if the guest wrote one) and the manifest."""
        inform(
            "Copying process_info.txt from m5.outdir "
            "to checkpoint path if it exists."
        )
        copy_file(
            "process_info.txt",
            get_outdir(),
            self._checkpoint_path,
        )
        if self._on_checkpoint is not None:
            self._on_checkpoint(self._checkpoint_path, board)

    def _validate_options(self, board: AbstractBoard):
        if self._take_checkpoint:
            if self._checkpoint_path is None:
                raise ValueError("Checkpoint base path is not provided.")
        if self._sample_stats:
            if self._sample_period == "none":
                raise ValueError(
                    "`sample_stats` is set but `sample_period` is none."
                )
        if self._sample_period != "none":
            if not self._sample_stats:
                raise ValueError(
                    "`sample_period` is set, but `sample_stats` is disabled."
                )

    def get_exit_event_handler(self, board: AbstractBoard):
        self._validate_options(board)
        return self._get_exit_event_handler(board)

    def _get_exit_event_handler(self, board: AbstractBoard):
        def handle_exit(board):
            num_exits_received = 0
            while True:
                inform("Received an exit.")
                num_exits_received += 1
                if num_exits_received == 1:
                    inform("It's from gem5_init.sh.")
                    inform("Continuing simulation past gem5_init.sh.")
                elif num_exits_received == 2:
                    inform("It's from after_boot.sh.")
                    inform("Continuing simulation past after_boot.sh.")
                else:
                    warn("Received an unexpected exit.")
                    yield SimStep.STOP
                yield SimStep.REMAINING_TIME

        def handle_max_tick(board):
            while not self._reacted_yet:
                inform("Received a `max_tick` before reacting to the ROI.")
                yield SimStep.REMAINING_TIME
            not_done = True
            while not_done:
                inform("Received a max_tick.")
                if self._sample_stats:
                    dump_stats()
                    inform("Dumped sim stats.")
                    yield self._sample_period
                else:
                    dump_stats()
                    not_done = False
                    yield SimStep.STOP
            raise RuntimeError("Did not expect a max_tick.")

        def handle_work_begin(board):
            processor = board.get_processor()
            can_switch = isinstance(processor, SwitchableProcessor)
            if self._has_warmup:
                inform("Received a work_begin.")
                if can_switch and processor.has_phase("warmup"):
                    processor.switch("warmup")
                    inform("Switched cpu without resetting stats.")
                yield SimStep.REMAINING_TIME
            inform("Received a work_begin.")
            reset_stats()
            inform("Reset sim stats.")
            if self._take_checkpoint:
                # Set before the manifest records the handler's state, so
                # that restoring the checkpoint continues inside the ROI.
                self._reacted_yet = True
                take_checkpoint(self._checkpoint_path)
                inform(f"Took a checkpoint in {self._checkpoint_path}.")
                self._after_checkpoint(board)
                yield SimStep.STOP
            else:
                if can_switch and processor.has_phase("main"):
                    processor.switch("main")
                    inform("Switched to the next processor.")
                    self._reacted_yet = True
                yield (
                    SimStep.REMAINING_TIME
                    if not self._sample_stats
                    else self._sample_period
                )
            raise RuntimeError("Did not expect a work_begin.")

        def handle_work_end(board):
            inform("Received a work_end.")
            dump_stats()
            inform("Dumped sim stats.")
            yield SimStep.STOP
            raise RuntimeError("Did not expect a work_end.")

        return {
            ExitEvent.EXIT: handle_exit(board),
            ExitEvent.MAX_TICK: handle_max_tick(board),
            ExitEvent.WORKBEGIN: handle_work_begin(board),
            ExitEvent.WORKEND: handle_work_end(board),
        }


class MPIExitEventHandlerWrapper(ExitEventHandlerWrapper):
    def __init__(
        self,
        num_processes: int,
        sample_stats: bool,
        sample_period: str,
        take_checkpoint: bool,
        checkpoint_base_path: Optional[Union[str, Path]],
        has_warmup: bool,
    ):
        super().__init__(
            sample_stats,
            sample_period,
            take_checkpoint,
            checkpoint_base_path,
            has_warmup,
        )
        self._num_processes = num_processes

    def _get_exit_event_handler(self, board: AbstractBoard):
        def handle_exit(board):
            num_exits_received = 0
            while True:
                inform("Received an exit.")
                num_exits_received += 1
                if num_exits_received == 1:
                    inform("It's from gem5_init.sh.")
                    inform("Continuing simulation past gem5_init.sh.")
                elif num_exits_received == 2:
                    inform("It's from after_boot.sh.")
                    inform("Continuing simulation past after_boot.sh.")
                else:
                    warn("Received an unexpected exit.")
                    yield SimStep.STOP
                yield SimStep.REMAINING_TIME

        def handle_max_tick(board):
            while not self._reacted_yet:
                inform("Received a `max_tick` before reacting to the ROI.")
                yield SimStep.REMAINING_TIME
            not_done = True
            while not_done:
                inform("Received a max_tick.")
                if self._sample_stats:
                    dump_stats()
                    inform("Dumped sim stats.")
                    yield self._sample_period
                else:
                    dump_stats()
                    not_done = False
                    yield SimStep.STOP
            raise RuntimeError("Did not expect a max_tick.")

        def handle_work_begin(board):
            processor = board.get_processor()
            can_switch = isinstance(processor, SwitchableProcessor)
            assert processor.get_num_cores() >= self._num_processes

            num_work_begin_received = 0
            warmed_up_yet = False
            while not self._reacted_yet:
                inform("Received a work_begin.")
                num_work_begin_received += 1
                inform(
                    f"Received {num_work_begin_received} work_begins so far."
                )
                if num_work_begin_received % self._num_processes == 0:
                    # The board holds the MSS flag (restored from the
                    # manifest), so count from its current value.
                    board.setMSSFlag(board.getMSSFlag() + 1)
                    if self._has_warmup and not warmed_up_yet:
                        if can_switch and processor.has_phase("warmup"):
                            processor.switch("warmup")
                            inform("Switched cpu without resetting stats.")
                        warmed_up_yet = True
                        yield SimStep.REMAINING_TIME
                    else:
                        reset_stats()
                        inform("Reset sim stats.")
                        if self._take_checkpoint:
                            # Set before the manifest records the handler's
                            # state, so that restoring the checkpoint
                            # continues inside the ROI.
                            self._reacted_yet = True
                            take_checkpoint(self._checkpoint_path)
                            inform(
                                f"Took a checkpoint in {self._checkpoint_path}."
                            )
                            self._after_checkpoint(board)
                            yield SimStep.STOP
                        else:
                            if can_switch and processor.has_phase("main"):
                                processor.switch("main")
                                inform("Switched to the next processor.")
                                self._reacted_yet = True
                            yield (
                                SimStep.REMAINING_TIME
                                if not self._sample_stats
                                else self._sample_period
                            )
                else:
                    yield SimStep.REMAINING_TIME
            raise RuntimeError(
                "Did not expect a work_begin. "
                f"Have already received {num_work_begin_received} "
                "from the desired region."
            )

        def handle_work_end(board):
            processor = board.get_processor()
            assert processor.get_num_cores() >= self._num_processes
            num_work_end_received = 0

            not_dumped_yet = True
            while not_dumped_yet:
                inform("Received a work_end.")
                num_work_end_received += 1
                inform(f"Received {num_work_end_received} work_ends so far.")
                if num_work_end_received == self._num_processes:
                    dump_stats()
                    inform("Dumped sim stats.")
                    not_dumped_yet = False
                    board.setMSSFlag(board.getMSSFlag() + 1)
                    yield SimStep.STOP
                else:
                    yield (
                        SimStep.REMAINING_TIME
                        if not self._sample_stats
                        else self._sample_period
                    )
            raise RuntimeError(
                "Did not expect a work_end. "
                f"Have already received {num_work_end_received} "
                "after entering the desired region."
            )

        return {
            ExitEvent.EXIT: handle_exit(board),
            ExitEvent.MAX_TICK: handle_max_tick(board),
            ExitEvent.WORKBEGIN: handle_work_begin(board),
            ExitEvent.WORKEND: handle_work_end(board),
        }


class FSWorkloadWrapper:
    @staticmethod
    def parse_args(args):
        raise NotImplementedError

    def __init__(
        self,
        cwd: str,
        binary_name: str,
        num_processes: int,
        has_warmup: bool,
    ):
        self._cwd = cwd
        self._binary_name = binary_name
        self._num_processes = num_processes
        self._has_warmup = has_warmup
        self._exit_handler = None

    def generate_cmdline(self):
        return (
            "#! /bin/bash\n\n"
            "# Changing directory to the right cwd.\n"
            f"cd {self._cwd}\n\n"
            "# Dumping the object file to a text file (truncate any old one).\n"
            'echo "objdump" > process_info.txt\n'
            f"objdump -S {self._binary_name} >> process_info.txt\n\n"
            "# Creating the directory for mmap_done.\n"
            f"mkdir -p {self._cwd}/mmap_done\n"
            "# Writing 0 to the mmap_done.txt file to indicate that mmap is not done yet.\n"
            f"echo 0 > {self._cwd}/mmap_done/mmap_done.txt\n\n"
            "# Exporting MMAP_DONE_PATH.\n"
            f"export MMAP_DONE_PATH={self._cwd}/mmap_done/mmap_done.txt\n"
            "# Exporting PID_DUMP_PATH.\n"
            f"export PID_DUMP_PATH={self._cwd}/pids\n\n"
            "# Running the command to launch workload.\n"
            f"{self._generate_cmdline()} &\n"
            "WL_PID=$!\n\n"
            f"# Storing process mmap to host.\n"
            "# Waiting for the PID_DUMP_PATH to be created.\n"
            "while true; do\n"
            "\tif [[ -d $PID_DUMP_PATH ]]; then\n"
            "\t\tnum_files=$(find $PID_DUMP_PATH -maxdepth 1 -name 'pid_*' | wc -l)\n"
            f"\t\tif [[ $num_files -eq {self._num_processes} ]]; then\n"
            "\t\t\tbreak\n"
            "\t\tfi\n"
            "\tfi\n"
            "\tsleep 0.0625\n"
            "done\n\n"
            "# Detecting all pids of the workload.\n"
            "RANK_PIDS=()\n"
            "for file in $PID_DUMP_PATH/pid_*; do\n"
            "\tpid=${file##*/pid_}\n"
            "\tRANK_PIDS+=($pid)\n"
            "done\n\n"
            "# Writing of the mmap of each pid to a text file on guest.\n"
            "for pid in ${RANK_PIDS[@]}; do\n"
            '\techo "PID: $pid" >> process_info.txt\n'
            '\techo "12345" | sudo -S cat /proc/$pid/maps >> process_info.txt\n'
            "done\n"
            "gem5-bridge --addr=0x10010000 writefile process_info.txt\n\n"
            "# Writing 1 to the mmap_done.txt file to indicate that mmap is done.\n"
            "echo 1 > $MMAP_DONE_PATH\n"
            "# Waiting for the workload to finish (wait on its PID so that\n"
            "# its exit code is returned; a bare `wait` always returns 0).\n"
            "wait $WL_PID\n"
            "ret=$?\n"
            'echo "Workload finished with exit code $ret"\n'
            "if [ $ret -ne 0 ]; then\n"
            '\techo "Workload failed! Checking dmesg..."\n'
            '\techo "12345" | sudo -S dmesg | tail -n 50\n'
            "fi\n"
        )

    def _generate_cmdline(self):
        raise NotImplementedError

    def generate_id_dict(self):
        raise NotImplementedError

    def generate_id_string(self):
        ret_id = ""
        for key, value in self.generate_id_dict().items():
            ret_id += f"{key.upper()}.{value}-"
        return ret_id[:-1]

    def _create_exit_event_handler(
        self,
        sample_stats: bool,
        sample_period: str,
        take_checkpoint: bool,
        checkpoint_path: Optional[Union[str, Path]],
    ):
        self._exit_handler = ExitEventHandlerWrapper(
            sample_stats,
            sample_period,
            take_checkpoint,
            checkpoint_path,
            self._has_warmup,
        )

    def get_exit_event_handler(
        self,
        board: AbstractBoard,
        sample_stats: bool,
        sample_period: str,
        take_checkpoint: bool,
        checkpoint_path: Optional[Union[str, Path]],
    ):
        self._create_exit_event_handler(
            sample_stats,
            sample_period,
            take_checkpoint,
            checkpoint_path,
        )
        if self._exit_handler is None:
            raise RuntimeError("Failed to create an exit event handler.")
        self._exit_handler._on_checkpoint = self._write_checkpoint_manifest
        return self._exit_handler.get_exit_event_handler(board)

    def _write_checkpoint_manifest(
        self, checkpoint_path: Path, board: AbstractBoard
    ) -> None:
        """Write the manifest of the checkpoint just taken in
        `checkpoint_path`, from the board and this workload only."""
        restored_from = board.get_checkpoint_path()
        manifest = write_manifest(
            checkpoint_path,
            artifacts={
                "kernel": board.get_kernel_path(),
                "disk_image": board.get_disk_image_path(),
                "bootloader": board.get_bootloader_path(),
            },
            workload=self.generate_id_dict(),
            variant=self.get_variant().value,
            kvm=any(
                core.is_kvm_core()
                for core in board.get_processor().get_cores()
            ),
            memory_size=board.get_memory().get_size(),
            # gem5 does not checkpoint the MSS flag, but the guest depends
            # on it, so it is recorded here and set again on restore.
            mss_flag=board.getMSSFlag(),
            restored_from=(
                None
                if restored_from is None
                else str(Path(restored_from).resolve())
            ),
            **self.checkpoint_state(),
        )
        inform(f"Wrote {manifest}.")

    def read_checkpoint_manifest(self, checkpoint_path: Path) -> dict:
        """The manifest of `checkpoint_path`, checked against this workload.

        A boot checkpoint only has to be of the same variant (hov boots a
        different machine); any other checkpoint has to be of this workload,
        with the same warmup.
        """
        manifest = read_manifest(checkpoint_path)
        if manifest["workload"]["name"] == "boot":
            expected = {"variant": self.get_variant().value}
        else:
            expected = {
                "workload": self.generate_id_dict(),
                "has_warmup": self._has_warmup,
            }
        for key, value in expected.items():
            if manifest[key] != value:
                raise ValueError(
                    f"{checkpoint_path} was taken with {key}={manifest[key]}, "
                    f"but this workload has {key}={value}."
                )
        return manifest

    def restore_checkpoint_manifest(
        self, manifest: dict, board: AbstractBoard
    ) -> None:
        """Continue from the state recorded in a restored checkpoint's
        `manifest`. Call it after `set_kernel_disk_workload` (which sets the
        checkpoint) and `get_exit_event_handler`.

        The exit handler continues from the state it had when the checkpoint
        was taken. The guest spins in annotate_synchronize_ until the MSS
        flag says the ROI may run, and gem5 does not checkpoint the flag, so
        the board starts with the recorded one (exit handlers count on from
        the board's value). The manifest, snippet, and process_info.txt are
        kept next to the results.

        If the checkpoint carries an insights snippet (insights_snippet.txt,
        written by workloads/eval-artifacts/insights/generate_insights.py),
        it is registered with the processor's O3 cores; other cores ignore
        it.
        """
        self._exit_handler.set_state(manifest["exit_handler"])
        board.set_mss_flag(manifest["mss_flag"])

        checkpoint_path = Path(board.get_checkpoint_path())
        for name in (MANIFEST_NAME, SNIPPET_NAME, "process_info.txt"):
            if (checkpoint_path / name).exists():
                shutil.copy(
                    checkpoint_path / name, get_outdir() / f"checkpoint_{name}"
                )

        if (checkpoint_path / SNIPPET_NAME).exists():
            self.add_workload_insights(
                board, (checkpoint_path / SNIPPET_NAME).read_text()
            )
            inform(f"Registered the insights in {SNIPPET_NAME}.")

    def add_workload_insights(self, board: AbstractBoard, snippet: str) -> None:
        """Register `snippet` (see workload_insights.py) with the board's
        processor: per function, its exit PC and labelled access sites; per
        indirect chain, its PCs and destination-register overrides."""
        access_sites, indirect_chains = process_snippet(snippet)
        processor = board.get_processor()
        for func_name, info in access_sites.items():
            processor.add_function_info(
                func_name,
                info["ret"],
                [site.label() for site in info["access_sites"]],
                [site.pc() for site in info["access_sites"]],
            )
        for indirect_chain in indirect_chains:
            name = (
                f"{indirect_chain[-1].label()}[{indirect_chain[0].label()}]"
                f"{indirect_chain[-1].label_version()}"
            )
            processor.add_indirect_chain(
                name, [inst.pc() for inst in indirect_chain]
            )
            for inst in indirect_chain:
                if inst.has_override():
                    processor.add_reg_index_override(inst.override())

    def init_mss_flag(self, restoring_checkpoint: bool):
        return -1

    def needs_hov_mem(self) -> bool:
        return False

    def get_variant(self) -> WorkloadVariant:
        """The variant of this workload; ref-only workloads are ref."""
        return getattr(self, "_variant", WorkloadVariant.REF)

    def get_disk_image_path(self) -> Path:
        """The disk image to boot this workload from (its variant's)."""
        return Path(DISK_IMAGES[self.get_variant()])

    @staticmethod
    def checkpoint_artifact_path(manifest: dict, role: str) -> Path:
        """The `role` artifact ("kernel", "disk_image", "bootloader") the
        checkpoint of `manifest` was taken with; raises if the file is gone
        or its md5 changed since."""
        return artifact_path(manifest, role)

    def checkpoint_state(self) -> dict:
        """State the guest depends on when a checkpoint is taken; stored in
        the checkpoint manifest and used again on restore."""
        return {
            "has_warmup": self._has_warmup,
            "exit_handler": self._exit_handler.get_state(),
        }


class FSMPIWorkloadWrapper(FSWorkloadWrapper):
    def __init__(
        self, cwd: str, binary_name: str, num_processes: int, has_warmup: bool
    ):
        super().__init__(cwd, binary_name, num_processes, has_warmup)

    def _create_exit_event_handler(
        self,
        sample_stats: bool,
        sample_period: str,
        take_checkpoint: bool,
        checkpoint_path: Optional[Union[str, Path]],
    ):
        self._exit_handler = MPIExitEventHandlerWrapper(
            self._num_processes,
            sample_stats,
            sample_period,
            take_checkpoint,
            checkpoint_path,
            self._has_warmup,
        )

    def init_mss_flag(self, restoring_checkpoint: bool):
        return (
            0 if not restoring_checkpoint else (2 if self._has_warmup else 1)
        )


class BootWrapper(FSWorkloadWrapper):
    class BootExitEventHandlerWrapper(ExitEventHandlerWrapper):
        def __init__(
            self,
            take_checkpoint: bool,
            checkpoint_path: Path,
        ):
            super().__init__(
                sample_stats=False,
                sample_period="none",
                take_checkpoint=take_checkpoint,
                checkpoint_path=checkpoint_path,
                has_warmup=False,
            )

        def _get_exit_event_handler(self, board):
            def handle_exit(board):
                inform("Received an exit.")
                inform("It's from gem5_init.sh.")
                inform("Continuing simulation past gem5_init.sh.")
                yield SimStep.REMAINING_TIME
                inform("It's from after_boot.sh.")
                if self._take_checkpoint:
                    inform("Taking a checkpoint")
                    take_checkpoint(self._checkpoint_path)
                    self._after_checkpoint(board)
                    yield SimStep.STOP
                else:
                    inform("Continuing simulation past after_boot.sh.")
                    yield SimStep.REMAINING_TIME
                warn("Received an unexpected exit.")
                yield SimStep.STOP

            return {
                ExitEvent.EXIT: handle_exit(board),
            }

    @staticmethod
    def parse_args(args):
        parser = argparse.ArgumentParser()
        # hov boots a different machine: Linux gets less memory and the hov
        # pool is passed on the kernel command line, so ref and hov workloads
        # each need their own boot checkpoint.
        parser.add_argument(
            "--variant",
            type=str,
            required=False,
            default="ref",
            choices=[variant.value for variant in WorkloadVariant],
        )
        parsed_args = parser.parse_args(args)
        return [WorkloadVariant(parsed_args.variant)]

    def __init__(self, variant: WorkloadVariant = WorkloadVariant.REF):
        super().__init__("/home/gem5", "", 1, False)
        self._variant = variant

    def generate_cmdline(self):
        return (
            "#! /bin/bash\n\n"
            f'# Disabling ASLR.\necho "12345" | sudo -S sysctl -w kernel.randomize_va_space=0\n\n'
            f"# Changing directory to the right cwd.\ncd {self._cwd}\n"
        )

    def _generate_cmdline(self):
        raise NotImplementedError

    def get_write_mmap_cmd(self):
        raise NotImplementedError

    def _create_exit_event_handler(
        self,
        sample_stats,
        sample_period,
        take_checkpoint,
        checkpoint_path,
    ):
        inform(
            "BootCommandWrapper ignores all of `sample_stats`, `sample_period`."
        )
        self._exit_handler = BootWrapper.BootExitEventHandlerWrapper(
            take_checkpoint,
            checkpoint_path,
        )

    def generate_id_dict(self):
        return {"name": "boot", "variant": self._variant.value}

    def needs_hov_mem(self) -> bool:
        return self._variant == WorkloadVariant.HOV

    @staticmethod
    def id_string_for(variant: WorkloadVariant) -> str:
        """ID string (checkpoint directory name) of the boot checkpoint for
        `variant`, e.g. NAME.boot-VARIANT.hov."""
        return BootWrapper(variant).generate_id_string()


class BransonWrapper(FSMPIWorkloadWrapper):
    _base_input_path = "/home/gem5/workloads/branson/inputs"
    _input_translator = {
        "hohlraum_single": "3D_hohlraum_single_node.xml",
        "hohlraum_single_shrunk": "3D_hohlraum_single_node_shrunk.xml",
        "hohlraum_multi": "3D_hohlraum_multi_node.xml",
        "hohlraum_multi_shrunk": "3D_hohlraum_multi_node_shrunk.xml",
        "cube_decomp": "cube_decomp_test.xml",
    }

    @staticmethod
    def parse_args(args):
        parser = argparse.ArgumentParser()
        parser.add_argument("--num-processes", type=int, required=True)
        parser.add_argument(
            "--input-name",
            type=str,
            required=True,
            choices=BransonWrapper._input_translator.keys(),
        )

        # Branson is ref-only: the hov variant is parked on branson's
        # sift-hov branch, so no BRANSON_hov binary is built.
        parser.add_argument(
            "--variant", type=str, required=True, choices=["ref"]
        )

        parsed_args = parser.parse_args(args)
        return [
            parsed_args.num_processes,
            parsed_args.input_name,
            WorkloadVariant(parsed_args.variant),
        ]

    def __init__(
        self,
        num_processes: int,
        input_name: str,
        variant: WorkloadVariant,
    ):
        binary_name = f"BRANSON_{variant.value}"
        super().__init__(
            "/home/gem5/workloads/branson/build",
            binary_name,
            num_processes,
            False,
        )
        self._input_name = BransonWrapper._input_translator[input_name]
        self._input_path = (
            f"{BransonWrapper._base_input_path}/{self._input_name}"
        )
        self._variant = variant

    def _generate_cmdline(self):
        workload_cmd = f"./{self._binary_name} {self._input_path}"
        return _mpirun_command_template.format(
            num_processes=self._num_processes,
            extra_args="",
            workload_cmd=workload_cmd,
        )

    def generate_id_dict(self):
        return {
            "name": "branson",
            "num-processes": self._num_processes,
            "input": self._input_name,
            "variant": self._variant.value,
        }

    def needs_hov_mem(self) -> bool:
        return self._variant == WorkloadVariant.HOV


class HPCGWrapper(FSMPIWorkloadWrapper):
    @staticmethod
    def parse_args(args):
        parser = argparse.ArgumentParser()
        parser.add_argument("--num-processes", type=int, required=True)
        parser.add_argument("--dim-x", type=int, required=True)
        parser.add_argument("--dim-y", type=int, required=True)
        parser.add_argument("--dim-z", type=int, required=True)
        parser.add_argument("--seconds", type=int, required=True)
        parser.add_argument("--kernel", type=str, required=True)
        parser.add_argument(
            "--variant", type=str, required=True, choices=["ref", "hov"]
        )

        parsed_args = parser.parse_args(args)
        return [
            parsed_args.num_processes,
            parsed_args.dim_x,
            parsed_args.dim_y,
            parsed_args.dim_z,
            parsed_args.seconds,
            parsed_args.kernel,
            WorkloadVariant(parsed_args.variant),
        ]

    def __init__(
        self,
        num_processes: int,
        dim_x: int,
        dim_y: int,
        dim_z: int,
        seconds: int,
        kernel: str,
        variant: WorkloadVariant,
    ):
        binary_name = f"xhpcg_{kernel}_{variant.value}_gem5fs"
        super().__init__(
            "/home/gem5/workloads/hpcg/bin", binary_name, num_processes, False
        )
        self._x = dim_x
        self._y = dim_y
        self._z = dim_z
        self._secs = seconds
        self._kernel = kernel
        self._variant = variant
        # ReadHpcgDat skips two header lines, then reads "nx ny nz" and the
        # run time; anything it can't read silently falls back to 16^3/1800s.
        self._write_dat = (
            "printf 'HPCG benchmark input file\\n"
            "Sandia National Laboratories; University of Tennessee, Knoxville\\n"
            "%d %d %d\\n%d\\n' "
            f"{self._x} {self._y} {self._z} {self._secs} > hpcg.dat"
        )

    def _generate_cmdline(self):
        return f"{self._write_dat};\n" + _mpirun_command_template.format(
            num_processes=self._num_processes,
            extra_args="",
            workload_cmd=f"./{self._binary_name}",
        )

    def generate_id_dict(self):
        return {
            "name": "hpcg",
            "num-processes": self._num_processes,
            "dim-x": self._x,
            "dim-y": self._y,
            "dim-z": self._z,
            "set-time": self._secs,
            "kernel": self._kernel,
            "variant": self._variant.value,
        }

    def needs_hov_mem(self) -> bool:
        return self._variant == WorkloadVariant.HOV


class UMEWrapper(FSMPIWorkloadWrapper):
    _base_input_path = "/home/gem5/workloads/UME/inputs"
    _input_translator = {
        "blake": ("blake/blake/blake", 1),
        "blakex128": ("blake/blake/blake.00128", 1),
        "pipe_3d": ("pipe_3d/pipe_3d/pipe_3d_00001", 8),
        "pipe_3dx2": ("pipe_3d/pipe_3d/pipe_3d_00001.00002", 8),
        "pipe_3dx4": ("pipe_3d/pipe_3d/pipe_3d_00001.00004", 8),
        "tgv": ("tgv/tgv/tgv_large_00001", 8),
    }
    _region_translator = {"gradzatz": 0, "gradzatz_invert": 1, "face_area": 2}

    @staticmethod
    def parse_args(args):
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--input-name",
            type=str,
            required=True,
            choices=UMEWrapper._input_translator.keys(),
        )
        parser.add_argument(
            "--region",
            type=str,
            required=True,
            choices=list(UMEWrapper._region_translator.keys()),
        )

        parser.add_argument(
            "--variant", type=str, required=True, choices=["ref", "hov"]
        )

        parsed_args = parser.parse_args(args)
        return [
            parsed_args.input_name,
            parsed_args.region,
            WorkloadVariant(parsed_args.variant),
        ]

    def __init__(
        self,
        input_name: str,
        region: str,
        variant: WorkloadVariant,
    ):
        input_file, num_processes = UMEWrapper._input_translator[input_name]
        binary_name = f"ume_mpi_{region}_{variant.value}"

        super().__init__(
            "/home/gem5/workloads/UME/build/src",
            binary_name,
            num_processes,
            True,
        )
        self._input_name = input_name
        self._input_file = input_file
        self._region_name = region
        self._variant = variant

    def _generate_cmdline(self):
        workload_cmd = (
            f"./{self._binary_name} "
            f"{UMEWrapper._base_input_path}/{self._input_file}"
        )
        mpi_extra_args = ""
        if self._variant == WorkloadVariant.HOV:
            mpi_extra_args = f"-x LD_PRELOAD={_hov_syscalls_lib} "
        return _mpirun_command_template.format(
            num_processes=self._num_processes,
            extra_args=mpi_extra_args,
            workload_cmd=workload_cmd,
        )

    def generate_id_dict(self):
        return {
            "name": "ume",
            "num-processes": self._num_processes,
            "input": self._input_name,
            "region": self._region_name,
            "variant": self._variant.value,
        }

    def needs_hov_mem(self) -> bool:
        return self._variant == WorkloadVariant.HOV


class NPBWrapper(FSWorkloadWrapper):

    @staticmethod
    def parse_args(args):
        parser = argparse.ArgumentParser()
        parser.add_argument("--workload", type=str, required=True)
        parser.add_argument("--size", type=str, required=True)

        parsed_args = parser.parse_args(args)
        return [parsed_args.workload, parsed_args.size]

    def __init__(
        self,
        workload: str,
        size: str,
    ):
        binary_name = f"{workload.lower()}.{size.upper()}.x"
        super().__init__(
            f"/home/gem5/workloads/NPB3.4-OMP/bin", f"{binary_name}", False
        )
        self._workload = workload.lower()
        self._size = size.upper()

    def _generate_cmdline(self):
        return f"./{self._binary_name}"

    def generate_id_dict(self):
        return {"name": "npb", "workload": self._workload, "size": self._size}


class MPINPBWrapper(FSMPIWorkloadWrapper):
    @staticmethod
    def parse_args(args):
        parser = argparse.ArgumentParser()
        parser.add_argument("--num-processes", type=int, required=True)
        parser.add_argument("--workload", type=str, required=True)
        parser.add_argument("--size", type=str, required=True)

        parsed_args = parser.parse_args(args)
        return [
            parsed_args.num_processes,
            parsed_args.workload,
            parsed_args.size,
        ]

    def __init__(self, num_processes: int, workload: str, size: str):
        binary_name = f"{workload.lower()}.{size.upper()}.x"
        super().__init__(
            "/home/gem5/workloads/NPB3.4-MPI/bin",
            binary_name,
            num_processes,
            False,
        )
        self._num_processes = num_processes
        self._workload = workload.lower()
        self._size = size.upper()

    def _generate_cmdline(self):
        workload_cmd = f"./{self._binary_name}"
        return _mpirun_command_template.format(
            num_processes=self._num_processes,
            extra_args="",
            workload_cmd=workload_cmd,
        )

    def generate_id_dict(self):
        return {
            "name": "npb-mpi",
            "num-processes": self._num_processes,
            "workload": self._workload,
            "size": self._size,
        }


class SimpleVectorWrapper(FSWorkloadWrapper):
    def __init__(
        self,
        cwd: str,
        binary_name: str,
        use_sve: Union[bool, str],
    ):
        self._processing_mode = (
            "sve" if try_convert_bool(use_sve) else "scalar"
        )
        suffix = "-sve.gem5fs" if try_convert_bool(use_sve) else ".gem5"
        super().__init__(cwd, binary_name + suffix, False)


class GUPSWrapper(SimpleVectorWrapper):
    @staticmethod
    def parse_args(args):
        parser = argparse.ArgumentParser()
        parser.add_argument("--num-elements", type=int, required=True)
        parser.add_argument("--updates-per-burst", type=int, required=True)
        parser.add_argument("--use-sve", type=str, required=True)

        parsed_args = parser.parse_args(args)
        return [
            parsed_args.num_elements,
            parsed_args.updates_per_burst,
            parsed_args.use_sve,
        ]

    def __init__(
        self,
        num_elements: int,
        updates_per_burst: int,
        use_sve: Union[bool, str],
    ):
        super().__init__(
            "/home/gem5/workloads/simple-vector-bench/gups/bin",
            "gups",
            use_sve,
        )
        self._num_elements = num_elements
        self._updates_per_burst = updates_per_burst

    def _generate_cmdline(self):
        return (
            f"./{self._binary_name} "
            f"{self._num_elements} "
            f"{self._updates_per_burst}"
        )

    def generate_id_dict(self):
        return {
            "name": "gups",
            "processing-mode": self._processing_mode,
            "num-elements": self._num_elements,
            "updates-per-burst": self._updates_per_burst,
        }


class PermutatingGatherWrapper(SimpleVectorWrapper):
    @staticmethod
    def parse_args(args):
        parser = argparse.ArgumentParser()
        parser.add_argument("--seed", type=int, required=True)
        parser.add_argument("--mod", type=int, required=True)
        parser.add_argument("--use-sve", type=str, required=True)

        parsed_args = parser.parse_args(args)
        return [parsed_args.seed, parsed_args.mod, parsed_args.use_sve]

    def __init__(
        self,
        seed: int,
        mod: int,
        use_sve: Union[bool, str],
    ):
        super().__init__(
            "/home/gem5/workloads/simple-vector-bench/"
            "permutating-gather/bin",
            "permutating-gather",
            use_sve,
        )
        self._seed = seed
        self._mod = mod

    def _generate_cmdline(self):
        return f"./{self._binary_name} {self._seed} {self._mod}"

    def generate_id_dict(self):
        return {
            "name": "permutating-gather",
            "processing-mode": self._processing_mode,
            "seed": self._seed,
            "mod": self._mod,
        }


class PermutatingScatterWrapper(SimpleVectorWrapper):
    @staticmethod
    def parse_args(args):
        parser = argparse.ArgumentParser()
        parser.add_argument("--seed", type=int, required=True)
        parser.add_argument("--mod", type=int, required=True)
        parser.add_argument("--use-sve", type=str, required=True)

        parsed_args = parser.parse_args(args)
        return [parsed_args.seed, parsed_args.mod, parsed_args.use_sve]

    def __init__(
        self,
        seed: int,
        mod: int,
        use_sve: Union[bool, str],
    ):
        super().__init__(
            "/home/gem5/workloads/simple-vector-bench/"
            "permutating-scatter/bin",
            "permutating-scatter",
            use_sve,
        )
        self._seed = seed
        self._mod = mod

    def _generate_cmdline(self):
        return f"./{self._binary_name} {self._seed} {self._mod}"

    def generate_id_dict(self):
        return {
            "name": "permutating-scatter",
            "processing-mode": self._processing_mode,
            "seed": self._seed,
            "mod": self._mod,
        }


class SpatterWrapper(SimpleVectorWrapper):
    _base_input_path = (
        "/home/gem5/workloads/simple-vector-bench/spatter-patterns"
    )
    _input_translator = {
        "flag": "001.json",
        "flag-nonfp": "001.nonfp.json",
        "flag-fp": "001.fp.json",
        "xrage": "spatter.json",
        "amg": "amg.json",
        "lulesh": "lulesh.json",
        "nekbone": "nekbone.json",
        "pennant": "pennant.json",
    }

    @staticmethod
    def parse_args(args):
        parser = argparse.ArgumentParser()
        parser.add_argument("--pattern_name", type=str, required=True)
        parser.add_argument("--use_sve", type=str, required=True)

        parsed_args = parser.parse_args(args)
        return [parsed_args.pattern_name, parsed_args.use_sve]

    def __init__(
        self,
        pattern_name: str,
        use_sve: Union[bool, str],
    ):
        super().__init__(
            "/home/gem5/workloads/simple-vector-bench/spatter/bin",
            "spatter",
            use_sve,
        )
        self._pattern_name = pattern_name
        self._json_file_path = (
            f"{SpatterWrapper._base_input_path}/"
            f"{SpatterWrapper._input_translator[self._pattern_name]}"
        )

    def _generate_cmdline(self):
        return f"./{self._binary_name} {self._json_file_path}"

    def generate_id_dict(self):
        return {
            "name": "spatter",
            "processing-mode": self._processing_mode,
            "pattern-name": self._pattern_name,
        }


class StreamWrapper(SimpleVectorWrapper):
    @staticmethod
    def parse_args(args):
        parser = argparse.ArgumentParser()
        parser.add_argument("--array_size", type=int, required=True)
        parser.add_argument("--use_sve", type=str, required=True)

        parsed_args = parser.parse_args(args)
        return [parsed_args.array_size, parsed_args.use_sve]

    def __init__(
        self,
        array_size,
        use_sve: Union[bool, str],
    ):
        super().__init__(
            "/home/gem5/workloads/simple-vector-bench/stream/bin",
            "stream",
            use_sve,
        )
        self._array_size = array_size

    def _generate_cmdline(self):
        return f"./{self._binary_name} {self._array_size}"

    def generate_id_dict(self):
        return {
            "name": "stream",
            "processing-mode": self._processing_mode,
            "array-size": self._array_size,
        }
