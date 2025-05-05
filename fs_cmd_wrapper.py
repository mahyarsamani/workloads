import argparse

from enum import Enum
from pathlib import Path
from typing import Optional, Union

from m5.simulate import checkpoint
from m5.stats import reset as reset_stats
from m5.stats import dump as dump_stats
from m5.util import inform

from gem5.components.boards.abstract_board import AbstractBoard
from gem5.components.processors.switchable_processor import SwitchableProcessor
from gem5.simulate.exit_event import ExitEvent
from gem5.simulate.exit_event_generators import SimStep


_mpirun_command_template = (
    "mpirun -np {num_processes} "
    "-mca coll basic,self,libnbc -mca btl self,vader --noprefix {workload_cmd}"
)


def take_checkpoint(checkpoint_path: Path):
    checkpoint(str(checkpoint_path))


class ExitEventHandlerWrapper:
    def __init__(
        self,
        sample_stats: bool,
        sample_period: str,
        take_checkpoint: bool,
        continue_after_checkpoint: bool,
        checkpoint_path: Optional[Union[Path, None]],
    ):
        self._sample_stats = sample_stats
        self._sample_period = sample_period
        self._take_checkpoint = take_checkpoint
        self._continue_after_checkpoint = continue_after_checkpoint
        self._checkpoint_path = checkpoint_path

    def _validate_options(self, board: AbstractBoard):
        if self._take_checkpoint:
            if self._checkpoint_path is None:
                raise ValueError("Checkpoint base path is not provided.")
            if isinstance(board.get_processor(), SwitchableProcessor):
                raise ValueError(
                    "Checkpointing is not supported with SwitchableProcessor."
                )
        if self._continue_after_checkpoint:
            inform("Continuing after checkpointing is enabled.")
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
            while True:
                inform("Received an exit. Continuing simulation.")
                yield SimStep.REMAINING_TIME

        def handle_max_tick():
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

        def handle_work_begin(processor):
            can_switch = isinstance(processor, SwitchableProcessor)
            assert can_switch != self._take_checkpoint
            inform("Received a work_begin.")
            reset_stats()
            inform("Reset sim stats.")
            if self._take_checkpoint:
                take_checkpoint(self._checkpoint_path)
                inform(f"Took a checkpoint in {self._checkpoint_path}.")
                if self._continue_after_checkpoint:
                    inform("Continuing after checkpointing.")
                yield (
                    SimStep.REMAINTIN_TIME
                    if self._continue_after_checkpoint
                    else SimStep.STOP
                )
            if can_switch:
                processor.switch()
                inform("Switched to the next processor.")
                yield SimStep.REMAINING_TIME
            raise RuntimeError("Did not expect a work_begin.")

        def handle_work_end():
            inform("Received a work_end.")
            dump_stats()
            inform("Dumped sim stats.")
            yield SimStep.STOP
            raise RuntimeError("Did not expect a work_end.")

        return {
            ExitEvent.EXIT: handle_exit(),
            ExitEvent.MAX_TICK: handle_max_tick(),
            ExitEvent.WORKBEGIN: handle_work_begin(board.get_processor()),
            ExitEvent.WORKEND: handle_work_end(),
        }


class MPIExitEventHandlerWrapper(ExitEventHandlerWrapper):
    def __init__(
        self,
        num_processes: int,
        sample_stats: bool,
        sample_period: str,
        take_checkpoint: bool,
        continue_after_checkpoint: bool,
        checkpoint_base_path: Optional[Union[str, Path]],
    ):
        super().__init__(
            sample_stats,
            sample_period,
            take_checkpoint,
            continue_after_checkpoint,
            checkpoint_base_path,
        )
        self._num_processes = num_processes

    def _get_exit_event_handler(self, board: AbstractBoard):
        def handle_exit():
            while True:
                inform("Received an exit. Continuing simulation.")
                yield SimStep.REMAINING_TIME

        def handle_max_tick():
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

        def handle_work_begin(processor):
            class Reaction(Enum):
                NO_REACTION = 0
                SWITCH = 1
                CHECKPOINT = 2

            can_switch = isinstance(processor, SwitchableProcessor)
            assert can_switch != self._take_checkpoint
            assert processor.get_num_cores() >= self._num_processes
            last_reaction = Reaction.NO_REACTION
            num_received_work_begins = 0
            num_expected_work_begins = self._num_processes

            while last_reaction == Reaction.NO_REACTION:
                inform("Received a work_begin.")
                num_received_work_begins += 1
                inform(
                    f"Received {num_received_work_begins} work_begins so far."
                )
                if num_received_work_begins == num_expected_work_begins:
                    reset_stats()
                    inform("Reset sim stats.")
                    if self._take_checkpoint:
                        take_checkpoint(self._checkpoint_path)
                        inform(
                            f"Took a checkpoint in {self._checkpoint_path}."
                        )
                        last_reaction = Reaction.CHECKPOINT
                    if can_switch:
                        processor.switch()
                        inform("Switched to the next processor.")
                        last_reaction = Reaction.SWITCH
                if last_reaction == Reaction.NO_REACTION:
                    yield SimStep.REMAINING_TIME
                if last_reaction == Reaction.SWITCH:
                    yield SimStep.REMAINING_TIME
                if last_reaction == Reaction.CHECKPOINT:
                    if self._continue_after_checkpoint:
                        yield SimStep.REMAINING_TIME
                    else:
                        yield SimStep.STOP

            raise RuntimeError(
                "Did not expect a work_begin. "
                f"Have already received {num_received_work_begins}."
            )

        def handle_work_end(processor):
            assert processor.get_num_cores() >= self._num_processes
            not_dumped_yet = True
            num_received_work_ends = 0
            num_expected_work_ends = self._num_processes

            while not_dumped_yet:
                inform("Received a work_end.")
                num_received_work_ends += 1
                inform(f"Received {num_received_work_ends} work_ends so far.")
                if num_received_work_ends == num_expected_work_ends:
                    dump_stats()
                    not_dumped_yet = False
                    yield SimStep.STOP
                yield SimStep.REMAINING_TIME

            raise RuntimeError(
                "Did not expect a work_end. "
                f"Have already received {num_received_work_ends}."
            )

        return {
            ExitEvent.EXIT: handle_exit(),
            ExitEvent.MAX_TICK: handle_max_tick(),
            ExitEvent.WORKBEGIN: handle_work_begin(board.get_processor()),
            ExitEvent.WORKEND: handle_work_end(board.get_processor()),
        }


class FSCommandWrapper:
    @staticmethod
    def parse_args(args):
        raise NotImplementedError

    def __init__(self, cwd: str, binary_name: str):
        self._cwd = cwd
        self._binary_name = binary_name
        self._exit_handler = None

    def generate_cmdline(self):
        return f"#!/bin/bash\ncd {self._cwd};\n{self._generate_cmdline()};\n"

    def _generate_cmdline(self):
        raise NotImplementedError

    def generate_id_dict(self):
        raise NotImplementedError

    def generate_id_string(self):
        ret_id = ""
        for key, value in self.generate_id_dict().items():
            ret_id += f"{key.upper()}.{value}-"
        return ret_id[:-1]

    def get_exit_event_handler(
        self,
        board: AbstractBoard,
        sample_stats: bool,
        sample_period: str,
        take_checkpoint: bool,
        continue_after_checkpoint: bool,
        checkpoint_path: Optional[Union[str, Path]],
    ):
        self._create_exit_event_handler(
            sample_stats,
            sample_period,
            take_checkpoint,
            continue_after_checkpoint,
            checkpoint_path,
        )
        if self._exit_handler is None:
            raise RuntimeError("Failed to create an exit event handler.")
        return self._exit_handler.get_exit_event_handler(board)

    def _create_exit_event_handler(
        self,
        sample_stats: bool,
        sample_period: str,
        take_checkpoint: bool,
        continue_after_checkpoint: bool,
        checkpoint_path: Optional[Union[str, Path]],
    ):
        self._exit_handler = ExitEventHandlerWrapper(
            sample_stats,
            sample_period,
            take_checkpoint,
            continue_after_checkpoint,
            checkpoint_path,
        )


class FSMPICommandWrapper(FSCommandWrapper):
    def __init__(self, cwd: str, binary_name: str, num_processes: int):
        super().__init__(cwd, binary_name)
        self._num_processes = int(num_processes)

    def _create_exit_event_handler(
        self,
        sample_stats: bool,
        sample_period: str,
        take_checkpoint: bool,
        continue_after_checkpoint: bool,
        checkpoint_path: Optional[Union[str, Path]],
    ):
        self._exit_handler = MPIExitEventHandlerWrapper(
            self._num_processes,
            sample_stats,
            sample_period,
            take_checkpoint,
            continue_after_checkpoint,
            checkpoint_path,
        )


class BransonCommandWrapper(FSMPICommandWrapper):
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
            choices=BransonCommandWrapper._input_translator.keys(),
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
        self._input_name = BransonCommandWrapper._input_translator[input_name]
        self._input_path = (
            f"{BransonCommandWrapper._base_input_path}/{self._input_name}"
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


class HPCGCommandWrapper(FSMPICommandWrapper):
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
        self._dat_content = (
            f"\n\n{self._x} {self._y} {self._z}\n{self._secs}\n"
        )
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


class UMECommandWrapper(FSMPICommandWrapper):
    _base_input_path = "/home/gem5/workloads/UME/inputs"
    _input_translator = {
        "blake": ("blake/blake", 1),
        "pipe_3d": ("pipe_3d/pipe_3d_00001", 8),
    }

    @staticmethod
    def parse_args(args):
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--input-name",
            type=str,
            required=True,
            choices=UMECommandWrapper._input_translator.keys(),
        )

        parsed_args = parser.parse_args(args)
        return [parsed_args.input_name]

    def __init__(
        self,
        input_name: str,
    ):
        input_file, num_processes = UMECommandWrapper._input_translator[
            input_name
        ]
        super().__init__(
            "/home/gem5/workloads/UME/build/src", "ume_mpi", num_processes
        )
        self._input_name = input_name
        self._input_file = input_file

    def _generate_cmdline(self):
        workload_cmd = (
            f"./{self._binary_name} "
            f"{UMECommandWrapper._base_input_path}/{self._input_file}"
        )
        return _mpirun_command_template.format(
            num_processes=self._num_processes, workload_cmd=workload_cmd
        )

    def generate_id_dict(self):
        return {
            "name": "ume",
            "num-processes": self._num_processes,
            "input": self._input_name,
        }


class NPBCommandWrapper(FSCommandWrapper):

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
        binary_name = f"{workload}.{size.upper()}.x"
        super().__init__(
            f"/home/gem5/workloads/NPB3.4-OMP/bin", f"{binary_name}"
        )
        self._workload = workload
        self._size = size.upper()

    def _generate_cmdline(self):
        return f"./{self._binary_name}"

    def generate_id_dict(self):
        return {"name": "npb", "workload": self._workload, "size": self._size}


class SimpleVectorWrapper(FSCommandWrapper):
    def __init__(
        self,
        cwd: str,
        binary_name: str,
        use_sve: Union[bool, str],
    ):
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

        self._processing_mode = (
            "sve" if try_convert_bool(use_sve) else "scalar"
        )
        suffix = "-sve.gem5fs" if try_convert_bool(use_sve) else ".gem5"
        super().__init__(cwd, binary_name + suffix)


class GUPSCommandWrapper(SimpleVectorWrapper):
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


class PermutatingGatherCommandWrapper(SimpleVectorWrapper):
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


class PermutatingScatterCommandWrapper(SimpleVectorWrapper):
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


class SpatterCommandWrapper(SimpleVectorWrapper):
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
            f"{SpatterCommandWrapper._base_input_path}/"
            f"{SpatterCommandWrapper._input_translator[self._pattern_name]}"
        )

    def _generate_cmdline(self):
        return f"./{self._binary_name} {self._json_file_path}"

    def generate_id_dict(self):
        return {
            "name": "spatter",
            "processing-mode": self._processing_mode,
            "pattern-name": self._pattern_name,
        }


class StreamCommandWrapper(SimpleVectorWrapper):
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
