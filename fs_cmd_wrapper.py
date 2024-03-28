from typing import Union


class FSCommandWrapper:
    def __init__(self, binary_path: str):
        self._binary_path = binary_path

    def generate_cmdline(self):
        raise NotImplementedError

    def generate_id_dict(self):
        raise NotImplementedError


class HPCGCommandWrapper(FSCommandWrapper):

    def __init__(
        self,
        num_processes: int,
        dim_x: int,
        dim_y: int,
        dim_z: int,
        seconds: int,
    ):
        super().__init__("/home/ubuntu/benchmarks/hpcg/bin/xhpcg")
        self._num_processes = num_processes
        self._x = dim_x
        self._y = dim_y
        self._z = dim_z
        self._secs = seconds
        self._dat_content = (
            f"\n\n{self._x} {self._y} {self._z}\n{self._secs}\n"
        )
        self._write_dat = f"echo {self._dat_content} > hpcg.dat;"

    def generate_cmdline(self):
        return (
            f"{self._write_dat}\n"
            f"mpirun -n {self._num_processes} {self._binary_path}"
        )

    def generate_id_dict(self):
        return {
            "name": "hpcg",
            "num_processes": self._num_processes,
            "dim_x": self._x,
            "dim_y": self._y,
            "dim_z": self._z,
            "set time": self.secs,
        }


class BransonCommandWrapper(FSCommandWrapper):
    _base_input_path = "/home/ubuntu/benchmarks/branson/inputs"
    _input_translator = {
        "hohlraum_single": "3D_hohlraum_multi_node.xml",
        "hohlraum_single_shrunk": "3D_hohlraum_single_node_shrunk.xml",
        "hohlraum_multi": "3D_hohlraum_multi_node.xml",
        "hohlraum_multi_shrunk": "3D_hohlraum_multi_node_shrunk.xml",
        "cube_decomp": "cube_decomp_test.xml",
    }

    def __init__(self, num_processes: int, input_name: str):
        super().__init__("/home/ubuntu/benchmarks/branson/build/BRANSON")
        self._num_processes = num_processes
        self._input_name = BransonCommandWrapper._input_translator[input_name]
        self._input_path = (
            f"{BransonCommandWrapper._base_input_path}/{self._input_name}"
        )

    def generate_cmdline(self):
        return (
            f"mpiexec -n {self._num_processes} "
            f"{self._binary_path} {self._input_path}"
        )

    def generate_id_dict(self):
        return {
            "name": "branson",
            "num_processes": self._num_processes,
            "input": self._input_name,
        }


class UMECommandWrapper(FSCommandWrapper):
    _base_input_path = "/home/ubuntu/benchmarks/UME/inputs"
    _input_translator = {
        "blake": ("blake/blake", 1),
        "pipe_3d": ("pipe_3d/pipe_3d_00001", 8),
    }

    def __init__(self, input_name: str):
        super().__init__("/home/ubuntu/benchmarks/UME/build/src/ume_mpi")
        self._input_name = input_name
        self._input_file, self._num_processes = (
            UMECommandWrapper._input_translator[input_name]
        )

    def generate_cmdline(self):
        return (
            f"mpirun -n {self._num_processes} "
            f"{self._binary_path} {self._input_file}"
        )

    def generate_id_dict(self):
        return {
            "name": "ume",
            "num_processes": self._num_processes,
            "input": self._input_name,
        }


class NPBCommandWrapper(FSCommandWrapper):
    def __init__(self, workload: str, size: str):
        self._workload = workload
        self._size = size
        binary_name = f"{workload}.{size}.x"
        super().__init__(
            f"/home/ubuntu/benchmarks/NPB3.4-OMP/bin/{binary_name}"
        )

    def generate_cmdline(self):
        return f"{self._binary_path}"

    def generate_id_dict(self):
        return {"name": "npb", "workload": self._workload, "size": self._size}


class SimpleVectorWrapper(FSCommandWrapper):
    def __init__(self, binary_path: str, use_sve: Union[bool, str]):
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
        suffix = "-sve.gem5" if try_convert_bool(use_sve) else ".gem5"
        super().__init__(binary_path + suffix)


class GUPSCommandWrapper(SimpleVectorWrapper):
    def __init__(
        self,
        num_elements: int,
        updates_per_burst: int,
        use_sve: Union[bool, str],
    ):
        super().__init__(
            "/home/ubuntu/benchmarks/simple-vector-bench/gups/bin/gups",
            use_sve,
        )
        self._num_elements = num_elements
        self._updates_per_burst = updates_per_burst

    def generate_cmdline(self):
        return (
            f"{self._binary_path} "
            f"{self._num_elements} "
            f"{self._updates_per_burst}"
        )

    def generate_id_dict(self):
        return {
            "name": "gups",
            "processing_mode": self._processing_mode,
            "num_elements": self._num_elements,
            "updates_per_burst": self._updates_per_burst,
        }


class PermutatingGatherCommandWrapper(SimpleVectorWrapper):
    def __init__(self, seed: int, mod: int, use_sve: Union[bool, str]):
        super().__init__(
            "/home/ubuntu/benchmarks/simple-vector-bench/"
            "permutating-gather/bin/permutating-gather",
            use_sve,
        )
        self._seed = seed
        self._mod = mod

    def generate_cmdline(self):
        return f"{self._binary_path} {self._seed} {self._mod}"

    def generate_id_dict(self):
        return {
            "name": "permutating-gather",
            "processing_mode": self._processing_mode,
            "seed": self._seed,
            "mod": self._mod,
        }


class PermutatingScatterCommandWrapper(SimpleVectorWrapper):
    def __init__(self, seed: int, mod: int, use_sve: Union[bool, str]):
        super().__init__(
            "/home/ubuntu/benchmarks/simple-vector-bench/"
            "permutating-scatter/bin/permutating-scatter",
            use_sve,
        )
        self._seed = seed
        self._mod = mod

    def generate_cmdline(self):
        return f"{self._binary_path} {self._seed} {self._mod}"

    def generate_id_dict(self):
        return {
            "name": "permutating-scatter",
            "processing_mode": self._processing_mode,
            "seed": self._seed,
            "mod": self._mod,
        }


class SpatterCommandWrapper(SimpleVectorWrapper):
    _base_input_path = (
        "/home/ubuntu/benchmarks/simple-vector-bench/spatter/patterns"
    )
    _input_translator = {
        "flag": "flag/static_2d/001.json",
        "flag-nonfp": "flag/static_2d/001.nonfp.json",
        "flag-fp": "flag/static_2d/001.fp.json",
        "xrage": "xrage/asteroid/spatter.json",
    }

    def __init__(self, pattern_name: str, use_sve: Union[bool, str]):
        super().__init__(
            "/home/ubuntu/benchmarks/simple-vector-bench/spatter/bin/spatter",
            use_sve,
        )
        self._pattern_name = pattern_name
        self._json_file_path = (
            f"{SpatterCommandWrapper._base_input_path}/"
            f"{SpatterCommandWrapper._input_translator[self._pattern_name]}"
        )

    def generate_cmdline(self):
        return f"{self._binary_path} {self._json_file_path}"

    def generate_id_dict(self):
        return {
            "name": "spatter",
            "processing_mode": self._processing_mode,
            "pattern_name": self._pattern_name,
        }


class StreamCommandWrapper(SimpleVectorWrapper):
    def __init__(self, array_size, use_sve: Union[bool, str]):
        super().__init__(
            "/home/ubuntu/benchmarks/simple-vector-bench/stream/bin/stream",
            use_sve,
        )
        self._array_size = array_size

    def generate_cmdline(self):
        return f"{self._binary_path} {self._array_size}"

    def generate_id_dict(self):
        return {
            "name": "stream",
            "processing_mode": self._processing_mode,
            "array_size": self._array_size,
        }
