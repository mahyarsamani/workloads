from .se_workload_wrapper import (
    SEExitHandler,
    test_load,
    test_store,
    test_forward,
    test_load_idx,
    dot_indirect,
    dot_indirect_sve,
    dot_indirect_hov,
    reduce_indirect,
    reduce_indirect_sve,
    reduce_indirect_hov,
    GapbsWrapper,
    NPBCGWrapper,
    UMEKernelWrapper,
    SpMVWrapper,
    spmv_stencil27_32,
    spmv_uniform_64k,
    gapbs_pr_u14,
    gapbs_pr_spmv_u14,
    gapbs_bfs_u14,
    npb_cg_S,
    npb_cg_B,
    ume_gradzatz_300k,
    ume_gradzatz_invert_300k,
    ume_gradzatp_invert_300k,
    ume_gradzatp_300k,
    share_inval,
    share_false,
)

from .fs_workload_wrapper import (
    WorkloadVariant,
    BootWrapper,
    HPCGWrapper,
    BransonWrapper,
    UMEWrapper,
    NPBWrapper,
    MPINPBWrapper,
    GUPSWrapper,
    PermutatingGatherWrapper,
    PermutatingScatterWrapper,
    SpatterWrapper,
    StreamWrapper,
)

# The SE evaluation inputs (se_workload_wrapper._evaluation_workloads), by
# name, e.g. gapbs_pr_uniform23, npb_cg_C, spmv_uniform_4m.
from .se_workload_wrapper import SE_EVALUATION_WORKLOADS

globals().update(SE_EVALUATION_WORKLOADS)
