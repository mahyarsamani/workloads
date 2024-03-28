from .microbench import workloads

from .fs_cmd_wrapper import HPCGCommandWrapper as HPCGWrapper
from .fs_cmd_wrapper import BransonCommandWrapper as BransonWrapper
from .fs_cmd_wrapper import UMECommandWrapper as UMEWrapper
from .fs_cmd_wrapper import NPBCommandWrapper as NPBWrapper
from .fs_cmd_wrapper import GUPSCommandWrapper as GUPSWrapper
from .fs_cmd_wrapper import (
    PermutatingGatherCommandWrapper as PermGatherWrapper,
)
from .fs_cmd_wrapper import (
    PermutatingScatterCommandWrapper as PermScatterWrapper,
)
from .fs_cmd_wrapper import SpatterCommandWrapper as SpatterWrapper
from .fs_cmd_wrapper import StreamCommandWrapper as StreamWrapper
