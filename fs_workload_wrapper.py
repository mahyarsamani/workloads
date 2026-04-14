from .workload_insights import process_snippet

import argparse
import os
import re

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
    "-mca coll basic,self,libnbc -mca btl self,vader --noprefix {workload_cmd}"
)


def get_outdir():
    return Path(m5_options.outdir)


def copy_file(file_name: str, src_dir: Path, dst_dir: Path):
    src_path = src_dir / file_name
    dst_path = dst_dir / file_name
    if src_path.exists():
        dst_path.write_text(src_path.read_text())


def take_checkpoint(checkpoint_path: Path):
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
        num_regions_to_skip: int,
        take_checkpoint: bool,
        restore_checkpoint: bool,
        checkpoint_path: Union[Path, None],
    ):
        if take_checkpoint and restore_checkpoint:
            raise ValueError(
                "Both `take_checkpoint` and `restore_checkpoint` "
                "can not be True at the same time."
            )
        self._sample_stats = sample_stats
        self._sample_period = sample_period
        self._num_regions_to_skip = (
            num_regions_to_skip if not restore_checkpoint else 0
        )
        self._num_regions_skipped = 0
        self._reacted_yet = restore_checkpoint
        self._take_checkpoint = take_checkpoint
        self._checkpoint_path = checkpoint_path

    def _validate_options(self, board: AbstractBoard):
        if self._take_checkpoint:
            if self._checkpoint_path is None:
                raise ValueError("Checkpoint base path is not provided.")
            if isinstance(board.get_processor(), SwitchableProcessor):
                raise ValueError(
                    "Checkpointing is not supported with SwitchableProcessor."
                )
        if self._sample_period != "none":
            if not self._sample_stats:
                raise ValueError(
                    "Sample period is set, but sample_stats is disabled."
                )

    def get_exit_event_handler(self, board: AbstractBoard):
        self._validate_options(board)
        return self._get_exit_event_handler(board)

    def _get_exit_event_handler(self, board: AbstractBoard):
        def handle_exit():
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

        def handle_max_tick():
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
            assert can_switch != self._take_checkpoint
            while self._num_regions_skipped < self._num_regions_to_skip:
                inform("Received a work_begin.")
                inform(
                    f"Have skipped {self._num_regions_skipped} regions so far."
                )
                yield SimStep.REMAINING_TIME
            inform(
                "Received a work_begin after having "
                f"skipped {self._num_regions_skipped} regions.\n"
                f"Needed to skip: {self._num_regions_to_skip}."
            )
            reset_stats()
            inform("Reset sim stats.")
            if self._take_checkpoint:
                take_checkpoint(self._checkpoint_path)
                inform(f"Took a checkpoint in {self._checkpoint_path}.")
                inform(
                    "Copying process_info.txt from m5.outdir "
                    "to checkpoint path if it exists."
                )
                copy_file(
                    "process_info.txt",
                    get_outdir(),
                    self._checkpoint_path,
                )
                self._reacted_yet = True
                inform(
                    "Set `_reacted_yet` to True although "
                    "it's probably not going to be used."
                )
                yield SimStep.STOP
            if can_switch:
                processor.switch()
                inform("Switched to the next processor.")
                self._reacted_yet = True
                yield (
                    SimStep.REMAINING_TIME
                    if not self._sample_stats
                    else self._sample_period
                )
            raise RuntimeError("Did not expect a work_begin.")

        def handle_work_end():
            while self._num_regions_skipped < self._num_regions_to_skip:
                inform("Received a work_end.")
                inform(
                    f"Have skipped {self._num_regions_skipped} regions so far."
                )
                self._num_regions_skipped += 1
                yield SimStep.REMAINING_TIME
            inform(
                "Received a work_end after having "
                f"skipped {self._num_regions_skipped} regions.\n"
                f"Needed to skip: {self._num_regions_to_skip}."
            )
            dump_stats()
            inform("Dumped sim stats.")
            yield SimStep.STOP
            raise RuntimeError("Did not expect a work_end.")

        return {
            ExitEvent.EXIT: handle_exit(),
            ExitEvent.MAX_TICK: handle_max_tick(),
            ExitEvent.WORKBEGIN: handle_work_begin(board),
            ExitEvent.WORKEND: handle_work_end(),
        }


class MPIExitEventHandlerWrapper(ExitEventHandlerWrapper):
    def __init__(
        self,
        num_processes: int,
        sample_stats: bool,
        sample_period: str,
        num_regions_to_skip: int,
        take_checkpoint: bool,
        restore_checkpoint: bool,
        checkpoint_base_path: Optional[Union[str, Path]],
    ):
        super().__init__(
            sample_stats,
            sample_period,
            num_regions_to_skip,
            take_checkpoint,
            restore_checkpoint,
            checkpoint_base_path,
        )
        self._mss_flag = 0
        self._num_processes = num_processes

    def _get_exit_event_handler(self, board: AbstractBoard):
        def handle_exit():
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
                    yield SimStep.Stop
                yield SimStep.REMAINING_TIME

        def handle_max_tick():
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
            assert can_switch != self._take_checkpoint
            assert processor.get_num_cores() >= self._num_processes

            num_work_begin_received = 0
            while self._num_regions_skipped < self._num_regions_to_skip:
                inform("Received a work_begin.")
                num_work_begin_received += 1
                inform(
                    f"Received {num_work_begin_received} work_begins so far."
                )
                inform(
                    f"Have skipped {self._num_regions_skipped} regions so far."
                )
                if num_work_begin_received % self._num_processes == 0:
                    self._mss_flag += 1
                    board.setMSSFlag(self._mss_flag)
                yield SimStep.REMAINING_TIME

            inform("Entered the desired region.")
            inform("Resetting the count of received work_begins.")
            num_work_begin_received = 0
            while not self._reacted_yet:
                inform("Received a work_begin.")
                num_work_begin_received += 1
                inform(
                    f"Received {num_work_begin_received} work_begins so far."
                )
                if num_work_begin_received == self._num_processes:
                    reset_stats()
                    inform("Reset sim stats.")
                    if self._take_checkpoint:
                        take_checkpoint(self._checkpoint_path)
                        inform(
                            f"Took a checkpoint in {self._checkpoint_path}."
                        )
                        inform(
                            "Copying process_info.txt from m5.outdir "
                            "to checkpoint path if it exists."
                        )
                        copy_file(
                            "process_info.txt",
                            get_outdir(),
                            self._checkpoint_path,
                        )
                        self._reacted_yet = True
                        inform(
                            "Set `_reacted_yet` to True although "
                            "it's probably not going to be used."
                        )
                        yield SimStep.STOP
                    if can_switch:
                        processor.switch()
                        inform("Switched to the next processor.")
                        self._reacted_yet = True
                        self._mss_flag += 1
                        board.setMSSFlag(self._mss_flag)
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

            while self._num_regions_skipped < self._num_regions_to_skip:
                inform("Received a work_end.")
                num_work_end_received += 1
                inform(f"Received {num_work_end_received} work_ends so far.")
                inform(
                    f"Have skipped {self._num_regions_skipped} regions so far."
                )
                if num_work_end_received % self._num_processes == 0:
                    inform(
                        "This work_end marks the end of the this current region."
                    )
                    self._num_regions_skipped += 1
                    self._mss_flag += 1
                    board.setMSSFlag(self._mss_flag)
                yield SimStep.REMAINING_TIME

            inform("Inside the desired region.")
            inform("Resetting the count of received work_ends.")
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
                    self._mss_flag += 1
                    board.setMSSFlag(self._mss_flag)
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
            ExitEvent.EXIT: handle_exit(),
            ExitEvent.MAX_TICK: handle_max_tick(),
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
        num_processes,
        num_regions_to_skip: int = 0,
    ):
        self._cwd = cwd
        self._binary_name = binary_name
        self._num_processes = num_processes
        self._num_regions_to_skip = num_regions_to_skip
        self._exit_handler = None

    def get_mss_flag(self):
        return 1

    def generate_cmdline(self):
        return (
            "#! /bin/bash\n\n"
            "# Disabling ASLR.\n"
            'echo "12345" | sudo -S sysctl -w kernel.randomize_va_space=0\n\n'
            "# Waiting for 10 minutes to make sure all services have started.\n"
            "# This will reduce interference with the workload.\n"
            'echo "Waiting for 120 seconds for services to start."\n'
            "sleep 120\n"
            'echo "Wait is over."\n\n'
            "# Changing directory to the right cwd.\n"
            f"cd {self._cwd}\n\n"
            "# Dumping the object file to a text file.\n"
            'echo "objdump" >> process_info.txt\n'
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
            f"{self._generate_cmdline()} &\n\n"
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
            "# Waiting for the workload to finish.\n"
            "wait\n"
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
        restore_checkpoint: bool,
        checkpoint_path: Optional[Union[str, Path]],
    ):
        self._exit_handler = ExitEventHandlerWrapper(
            sample_stats,
            sample_period,
            self._num_regions_to_skip,
            take_checkpoint,
            restore_checkpoint,
            checkpoint_path,
        )

    def get_exit_event_handler(
        self,
        board: AbstractBoard,
        sample_stats: bool,
        sample_period: str,
        take_checkpoint: bool,
        restore_checkpoint: bool,
        checkpoint_path: Optional[Union[str, Path]],
    ):
        self._create_exit_event_handler(
            sample_stats,
            sample_period,
            take_checkpoint,
            restore_checkpoint,
            checkpoint_path,
        )
        if self._exit_handler is None:
            raise RuntimeError("Failed to create an exit event handler.")
        return self._exit_handler.get_exit_event_handler(board)

    def add_workload_insights(self, board: AbstractBoard) -> None:
        pass


class FSMPIWorkloadWrapper(FSWorkloadWrapper):
    def __init__(
        self,
        cwd: str,
        binary_name: str,
        num_processes: int,
        num_regions_to_skip: int = 0,
    ):
        super().__init__(cwd, binary_name, num_processes, num_regions_to_skip)

    def _create_exit_event_handler(
        self,
        sample_stats: bool,
        sample_period: str,
        take_checkpoint: bool,
        restore_checkpoint: bool,
        checkpoint_path: Optional[Union[str, Path]],
    ):
        self._exit_handler = MPIExitEventHandlerWrapper(
            self._num_processes,
            sample_stats,
            sample_period,
            self._num_regions_to_skip,
            take_checkpoint,
            restore_checkpoint,
            checkpoint_path,
        )


class BootWrapper(FSWorkloadWrapper):
    class BootExitEventHandlerWrapper(ExitEventHandlerWrapper):
        def __init__(self):
            super().__init__(
                sample_stats=False,
                sample_period="none",
                take_checkpoint=False,
                restore_checkpoint=False,
                num_regions_to_skip=0,
                checkpoint_path=None,
            )

        def _get_exit_event_handler(self, board):
            def handle_exit():
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

            return {
                ExitEvent.EXIT: handle_exit(),
            }

    @staticmethod
    def parse_args(args):
        inform("BootCommandWrapper does not accept any arguments.")
        return []

    def __init__(self):
        super().__init__("/home/gem5", "", 1)

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
        restore_checkpoint,
        checkpoint_path,
    ):
        inform(
            "BootCommandWrapper ignores all of `sample_stats`, "
            "`sample_period`, `take_checkpoint`, `checkpoint_path`."
        )
        self._exit_handler = BootWrapper.BootExitEventHandlerWrapper()

    def generate_id_dict(self):
        return {"name": "boot"}


class MPIBenchWrapper(FSMPIWorkloadWrapper):
    @staticmethod
    def parse_args(args):
        parser = argparse.ArgumentParser()
        parser.add_argument("--num-processes", type=int, required=True)
        parser.add_argument("--use-sve", type=str, required=True)

        parsed_args = parser.parse_args(args)
        return [parsed_args.num_processes, parsed_args.use_sve]

    def __init__(
        self,
        num_processes: int,
        use_sve: Union[bool, int, str],
    ):
        binary_name = (
            "mpi_bench_gem5_sve"
            if try_convert_bool(use_sve)
            else "mpi_bench_gem5"
        )
        super().__init__(
            "/home/gem5/workloads/mpi_bench", binary_name, num_processes
        )
        self._use_sve = try_convert_bool(use_sve)

    def _generate_cmdline(self):
        workload_cmd = f"./{self._binary_name} index.txt data.txt"
        return _mpirun_command_template.format(
            num_processes=self._num_processes, workload_cmd=workload_cmd
        )

    def generate_id_dict(self):
        return {
            "name": "mpi-bench",
            "use-sve": self._use_sve,
            "num-processes": self._num_processes,
        }


class BransonWrapper(FSMPIWorkloadWrapper):
    _base_input_path = "/home/gem5/workloads/branson/inputs"
    _input_translator = {
        "hohlraum_single": "3D_hohlraum_single_node.xml",
        "hohlraum_single_shrunk": "3D_hohlraum_single_node_shrunk.xml",
        "hohlraum_multi": "3D_hohlraum_multi_node.xml",
        "hohlraum_multi_shrunk": "3D_hohlraum_multi_node_shrunk.xml",
        "cube_decomp": "cube_decomp_test.xml",
    }

    snippet = """
offset: aaaaaaaa0000
func transport_photon:
    e404:   ldp@0       w20, w3, [x27]      label:  phtn                main
    e410:   sub         w5, w20, w4
    e424:   umaddl      x20, w5, w1, x2
    e470:   ldr         d12, [x20, #152]    label:  cell                main

    e584: ldr  x3, [sp, #176]               label:  phtn                main
    e590: lsl  x5, x3, #4
    e594: add  x6, x28, x5
    e5ac: ldr  d6,  [x6,  #8]               label: cell_tallies         main
ret e658

func main
ret b17c
"""

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

        parsed_args = parser.parse_args(args)
        return [
            parsed_args.num_processes,
            parsed_args.input_name,
        ]

    def __init__(
        self,
        num_processes: int,
        input_name: str,
    ):
        super().__init__(
            "/home/gem5/workloads/branson/build", "BRANSON", num_processes
        )
        self._input_name = BransonWrapper._input_translator[input_name]
        self._input_path = (
            f"{BransonWrapper._base_input_path}/{self._input_name}"
        )
        self._access_sites, self._indirect_chains = process_snippet(
            BransonWrapper.snippet
        )

    def _generate_cmdline(self):
        workload_cmd = f"./{self._binary_name} {self._input_path}"
        return _mpirun_command_template.format(
            num_processes=self._num_processes, workload_cmd=workload_cmd
        )

    def generate_id_dict(self):
        return {
            "name": "branson",
            "num-processes": self._num_processes,
            "input": self._input_name,
        }

    def add_workload_insights(self, board: AbstractBoard) -> None:
        processor = board.get_processor()
        for func_name, info in self._access_sites.items():
            labels = [site.label() for site in info["access_sites"]]
            pcs = [site.pc() for site in info["access_sites"]]
            processor.add_function_info(
                func_name,
                info["ret"],
                labels,
                pcs,
            )

        for indirect_chain in self._indirect_chains:
            name = f"{indirect_chain[-1].label()}[{indirect_chain[0].label()}]{indirect_chain[-1].label_version()}"
            processor.add_indirect_chain(
                name, [inst.pc() for inst in indirect_chain]
            )

            for override in [
                inst.override()
                for inst in indirect_chain
                if inst.has_override()
            ]:
                processor.add_reg_index_override(override)


class HPCGWrapper(FSMPIWorkloadWrapper):
    snippet = """
offset: aaaaaaaa0000
func ComputeSPMV_ref
    21880:  ldrsw   x1, [x4, x0, lsl #2]        label:  cur_inds        main
    2188c:  ldr     d1, [x5, x1, lsl #3]        label:  xv              main
ret 218bc

func ComputeSYMGS_ref
    21990:  ldrsw x2, [x7, x0, lsl #2]          label:  currColInd      main
    2199c:  ldr   d1, [x1, x2, lsl #3]          label:  xv@0            main

    219f0:  ldrsw x2, [x6, x0, lsl #2]          label:  currColInd      main
    219fc:  ldr   d1, [x1, x2, lsl #3]          label:  xv@1            main
ret 21a34

func ComputeRestriction_ref
    21f20:  ldrsw x1, [x6, x0, lsl #2]          label:  f2c             main
    21f24:  ldr   d0, [x4, x1, lsl #3]          label:  rf              main

    21f20:  ldrsw x1, [x6, x0, lsl #2]          label:  f2c             main
    21f28:  ldr   d1, [x3, x1, lsl #3]          label:  Axf             main
ret 21f44

func ComputeProlongation_ref
    21ec8:  ldrsw x1, [x5, x0, lsl #2]          label:  f2c             main
    21ed4:  ldr   d0, [x2, x1, lsl #3]          label:  xfv             main
ret 21eec
"""

    @staticmethod
    def parse_args(args):
        parser = argparse.ArgumentParser()
        parser.add_argument("--num-processes", type=int, required=True)
        parser.add_argument("--dim-x", type=int, required=True)
        parser.add_argument("--dim-y", type=int, required=True)
        parser.add_argument("--dim-z", type=int, required=True)
        parser.add_argument("--seconds", type=int, required=True)

        parsed_args = parser.parse_args(args)
        return [
            parsed_args.num_processes,
            parsed_args.dim_x,
            parsed_args.dim_y,
            parsed_args.dim_z,
            parsed_args.seconds,
        ]

    def __init__(
        self,
        num_processes: int,
        dim_x: int,
        dim_y: int,
        dim_z: int,
        seconds: int,
    ):
        super().__init__(
            "/home/gem5/workloads/hpcg/bin", "xhpcg", num_processes
        )
        self._x = dim_x
        self._y = dim_y
        self._z = dim_z
        self._secs = seconds
        self._dat_content = f'"{self._x} {self._y} {self._z}\\n{self._secs}"'
        self._write_dat = f"echo {self._dat_content} > hpcg.dat"

    def _generate_cmdline(self):
        return f"{self._write_dat};\n" + _mpirun_command_template.format(
            num_processes=self._num_processes,
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
        }


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

    gradzatz = """
offset: aaaaaaaa0000
func gradzatp:
    2d4bc:  ldr     w1, [x1, x0, lsl #2]    label:  c_to_p_map          main
    2d4c4:  sxtw    x6, w1
    2d4d4:  ldr     d0, [x7, x6, lsl #3]    label:  point_volume        gradzatp

    2d4bc:  ldr     w1, [x1, x0, lsl #2]    label:  c_to_p_map          main
    2d4d0:  smull   x1, w1, w12
    2d4f8:  ldr     q0, [x3, x1]            label:  point_gradient@0    main

    2d4bc:  ldr     w1, [x1, x0, lsl #2]    label:  c_to_p_map          main
    2d4d0:  smull   x1, w1, w12
    2d4ec:  add     x4, x3, x1
    2d50c:  ldr     d0, [x4, #16]           label:  point_gradient@1    main

    2d4e4:  ldr     w11, [x4, x0, lsl #2]   label:  c_to_z_map          main
    2d4fc:  ldr     d1, [x10, w11, sxtw #3] label:  zone_field          main
ret 2d628

func gradzatz:
    2dbac:  ldrsw   x1, [x1, x0, lsl #2]    label:  c_to_z_map          main
    2dbb4:  ldr     d0, [x20, x1, lsl #3]   label:  zone_volume@0       gradzatz

    2dd1c:  ldr     w1, [x1, x0, lsl #2]    label:  c_to_z_map          main
    2dd28:  ldr     d1, [x20, w1, sxtw #3]  label:  zone_volume@1       gradzatz

    2dd1c:  ldr     w1, [x1, x0, lsl #2]    label:  c_to_z_map          main
    2dd2c:  smull   x1, w1, w6
    2dd44:  ldr     q1, [x3, x1]            label:  zone_gradient@0     main

    2dd1c:  ldr     w1, [x1, x0, lsl #2]    label:  c_to_z_map          main
    2dd2c:  smull   x1, w1, w6
    2dd4c:  add	    x4, x3, x1
    2dd60:  ldr	    d1, [x4, #16]           label:  zone_gradient@1     main

    2dfd8:  ldr 	w2, [x2, x0, lsl #2]    label:  c_to_p_map          main
    2dfe8:  smull   x2, w2, w6
    2dff8:  ldr 	q3, [x5, x2]            label:  point_gradient@0    main

    2dd30:  ldr 	w2, [x2, x0, lsl #2]    label:  c_to_p_map          main
    2dd40:  smull   x2, w2, w6
    2dd48:  add	    x8, x5, x2
    2dd54:  ldr	    d2, [x8, #16]           label:  point_gradient@1    main
ret 2dea0

func main:
ret c134
"""

    gradzatz_invert = """
offset: aaaaaaaa0000
func gradzatp_invert:
    2c5f0:  ldr	    w3, [x17, x3, lsl #2]   label: c_to_z_map           main
    2c5fc:  ldr	    d2, [x9, w3, sxtw #3]   label: zone_field           main
ret 2c734

func gradzatz_invert:
    2ce00:  ldr 	w1, [x13, x1, lsl #2]   label:  c_to_p_map          main
    2ce08:  smull   x1, w1, w9
    2ce10:	ldr     q4, [x5, x1]            label:  point_gradient@0    main

    2ce00:  ldr 	w1, [x13, x1, lsl #2]   label:  c_to_p_map          main
    2ce08:  smull   x1, w1, w9
    2ce0c:  add 	x7, x5, x1
    2ce14:  ldr 	d5, [x7, #16]           label:  point_gradient@1    main
ret 2ce74

func main:
ret c134
"""

    face_area = """
offset: aaaaaaaa0000
func face_area:
    2bfa0:  ldrsw   x4, [x4, x2, lsl #2]    label:  s_to_f_map          main
    2bfd0:  ldr	    d3, [x0, x4, lsl #3]    label:  face_area           main

    2bfd4:  ldrsw   x6, [x8, x6]            label:  s_to_s2_map         main
    2bff0:  str     w9, [x20, x6, lsl #2]   label:  side_tag            face_area
ret 2c098

func main:
ret c134
"""
    snippet_translator = {
        "gradzatz": gradzatz,
        "gradzatz_invert": gradzatz_invert,
        "face_area": face_area,
    }

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

        parsed_args = parser.parse_args(args)
        return [parsed_args.input_name, parsed_args.region]

    def __init__(
        self,
        input_name: str,
        region: str,
    ):
        input_file, num_processes = UMEWrapper._input_translator[input_name]
        super().__init__(
            "/home/gem5/workloads/UME/build/src",
            "ume_mpi",
            num_processes,
            UMEWrapper._region_translator[region],
        )
        self._input_name = input_name
        self._input_file = input_file
        self._region_name = region
        self._access_sites, self._indirect_chains = process_snippet(
            UMEWrapper.snippet_translator[region]
        )

    def get_mss_flag(self):
        if self._region_name == "gradzatz":
            return 1
        elif self._region_name == "gradzatz_invert":
            return 3
        elif self._region_name == "face_area":
            return 5

    def _generate_cmdline(self):
        workload_cmd = (
            f"./{self._binary_name} "
            f"{UMEWrapper._base_input_path}/{self._input_file}"
        )
        return _mpirun_command_template.format(
            num_processes=self._num_processes, workload_cmd=workload_cmd
        )

    def generate_id_dict(self):
        return {
            "name": "ume",
            "num-processes": self._num_processes,
            "input": self._input_name,
            "region": self._region_name,
        }

    def add_workload_insights(self, board: AbstractBoard) -> None:
        processor = board.get_processor()
        for func_name, info in self._access_sites.items():
            labels = [site.label() for site in info["access_sites"]]
            pcs = [site.pc() for site in info["access_sites"]]
            processor.add_function_info(
                func_name,
                info["ret"],
                labels,
                pcs,
            )

        for indirect_chain in self._indirect_chains:
            name = f"{indirect_chain[-1].label()}[{indirect_chain[0].label()}]{indirect_chain[-1].label_version()}"
            processor.add_indirect_chain(
                name, [inst.pc() for inst in indirect_chain]
            )

            for override in [
                inst.override()
                for inst in indirect_chain
                if inst.has_override()
            ]:
                processor.add_reg_index_override(override)


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
            f"/home/gem5/workloads/NPB3.4-OMP/bin", f"{binary_name}"
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
            "/home/gem5/workloads/NPB3.4-MPI/bin", binary_name, num_processes
        )
        self._num_processes = num_processes
        self._workload = workload.lower()
        self._size = size.upper()

    def _generate_cmdline(self):
        workload_cmd = f"./{self._binary_name}"
        return _mpirun_command_template.format(
            num_processes=self._num_processes, workload_cmd=workload_cmd
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
        super().__init__(cwd, binary_name + suffix)


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
