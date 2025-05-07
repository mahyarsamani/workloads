#!/bin/bash

# Initialize variables
MACHINE=""
CONFIG="socket"
SUFFIX=""
WORKLOAD=""
SIZE=""
NUM_PROCS="8"

unset DISPLAY
export OMPI_MCA_plm=^rsh
# All benchmarks
all_benchmarks=(bt.A.x cg.A.x dt.A.x ep.A.x ft.A.x is.A.x lu.A.x mg.A.x sp.A.x 
            bt.B.x cg.B.x dt.B.x ep.B.x ft.B.x is.B.x lu.B.x mg.B.x sp.B.x 
            bt.D.x cg.D.x ep.D.x ft.D.x is.C.x lu.D.x mg.D.x sp.D.x 
            )

# Valid workloads
valid_workloads=(bt cg dt ep ft is lu mg sp)

# Print help message
print_help() {
  echo "Usage: ./run.sh --machine MACHINE --config CONFIG --suffix SUFFIX --workload WORKLOAD --size SIZE"
  echo ""
  echo "Options:"
  echo "  --machine MACHINE   Specify the machine name."
  echo "  --config CONFIG     Specify the config. Possible values are 'socket' and 'eight-core-def'. Default is 'socket'."
  echo "  --suffix SUFFIX     Specify the suffix."
  echo "  --workload WORKLOAD Specify a comma-separated list of workloads. Possible values are 'bt', 'cg', 'dt', 'ep', 'ft', 'is', 'lu', 'mg', and 'sp'."
  echo "  --size SIZE         Specify a comma-separated list of sizes. Possible values are 'A', 'B', and 'D'."
  echo "  --nprocs NUM_PROCS     Specify the number of MPI processes to use (default is unset)."
  echo ""
  echo "Example:"
  echo "  ./run.sh --machine grace --config eight-core-def --suffix test --workload bt,cg --size A,B"
}

# Parse command line arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --machine) MACHINE="$2"; shift ;;
        --config) CONFIG="$2"; shift ;;
        --suffix) SUFFIX="$2"; shift ;;
        --workload) IFS=',' read -ra WORKLOAD <<< "$2"; shift ;;
        --size) IFS=',' read -ra SIZE <<< "$2"; shift ;;
        --nprocs) NUM_PROCS="$2"; shift ;;
        *) echo "Unknown parameter passed: $1"; print_help; exit 1 ;;
    esac
    shift
done

# Check if machine, suffix, workload, and size are set
if [[ -z "$MACHINE" || -z "$SUFFIX" || -z "$WORKLOAD" || -z "$SIZE" || -z "$NUM_PROCS" ]]; then
    echo "Error: --machine, --suffix, --workload, and --size parameters are required."
    print_help
    exit 1
fi

# Check if config is valid
if [[ "$CONFIG" != "socket" && "$CONFIG" != "eight-core-def" ]]; then
    echo "Error: Invalid config. Possible values are 'socket' and 'eight-core-def'."
    print_help
    exit 1
fi

# Check if workload is valid
for workload in "${WORKLOAD[@]}"; do
    if ! printf '%s\n' "${valid_workloads[@]}" | grep -q -P "^$workload$"; then
        echo "Error: Invalid workload '$workload'. Possible values are 'bt', 'cg', 'dc', 'ep', 'ft', 'is', 'lu', 'mg', 'sp', and 'ua'."
        print_help
        exit 1
    fi
done

# Create all possible combinations of workload and size
benchmarks=()
for workload in "${WORKLOAD[@]}"; do
    for size in "${SIZE[@]}"; do
        combination="${workload}.${size}.x"
        # Check if the combination exists in all_benchmarks
        if printf '%s\n' "${all_benchmarks[@]}" | grep -q -P "^$combination$"; then
            benchmarks+=("$combination")
        fi
    done
done

# Print the machine, config, suffix, workload, size, and benchmarks
echo "Machine: $MACHINE"
echo "Config: $CONFIG"
echo "Suffix: $SUFFIX"
echo "Workload: ${WORKLOAD[*]}"
echo "Size: ${SIZE[*]}"
echo "Benchmarks: ${benchmarks[*]}"

export LD_LIBRARY_PATH=${PWD}/../annotate/papi/install/lib:$LD_LIBRARY_PATH


for bm in ${benchmarks[@]}; do
    echo $bm
    export PAPI_EVENTS="PAPI_L1_DCR,PAPI_L1_DCW,PAPI_L1_DCM,PAPI_L1_DCA,PAPI_TLB_DM"
    export PAPI_OUTPUT_DIRECTORY=${PWD}/../data/${MACHINE}-${CONFIG}-${SUFFIX}/npb_mpi/$bm/backend0_data
    echo "backend0"
    if [[ "$bm" == dt.* ]]; then
        
        mpirun -np $NUM_PROCS bin/$bm BH
    elif [[ "$CONFIG" == "eight-core-def" ]]; then
        numactl --physcpubind=0,1,2,3,4,5,6,7 --membind=0 -- mpirun -np $NUM_PROCS bin/$bm || numactl --physcpubind=0,1,2,3,4,5,6,7 --membind=0 -- mpirun bin/$bm
    else
        mpirun -np $NUM_PROCS bin/$bm 
    fi
    export PAPI_EVENTS="PAPI_L2_TCR,PAPI_L2_TCW,PAPI_L2_TCM,PAPI_L2_TCA,PAPI_L3_DCM,PAPI_L3_TCA"
    export PAPI_OUTPUT_DIRECTORY=${PWD}/../data/${MACHINE}-${CONFIG}-${SUFFIX}/npb_mpi/$bm/backend1_data
    echo "backend1"
    if [[ "$bm" == dt.* ]]; then
        
        mpirun -np $NUM_PROCS bin/$bm BH
    fi
    if [[ "$CONFIG" == "eight-core-def" ]]; then
        numactl --physcpubind=0,1,2,3,4,5,6,7 --membind=0 -- mpirun -np $NUM_PROCS bin/$bm || numactl --physcpubind=0,1,2,3,4,5,6,7 --membind=0 -- mpirun bin/$bm
    else
        mpirun -np $NUM_PROCS bin/$bm 
    fi
    export PAPI_EVENTS="PAPI_L1_ICM,PAPI_L1_ICH,PAPI_L1_ICA,PAPI_TLB_IM"
    export PAPI_OUTPUT_DIRECTORY=${PWD}/../data/${MACHINE}-${CONFIG}-${SUFFIX}/npb_mpi/$bm/frontend_data
    echo "frontend"
    if [[ "$bm" == dt.* ]]; then
        
        mpirun -np $NUM_PROCS bin/$bm BH
    fi
    if [[ "$CONFIG" == "eight-core-def" ]]; then
        numactl --physcpubind=0,1,2,3,4,5,6,7 --membind=0 -- mpirun -np $NUM_PROCS bin/$bm || numactl --physcpubind=0,1,2,3,4,5,6,7 --membind=0 -- mpirun bin/$bm
    else
        mpirun -np $NUM_PROCS bin/$bm 
    fi
    export PAPI_EVENTS="PAPI_TOT_INS,PAPI_INT_INS,PAPI_FP_INS,PAPI_LD_INS"
    export PAPI_OUTPUT_DIRECTORY=${PWD}/../data/${MACHINE}-${CONFIG}-${SUFFIX}/npb_mpi/$bm/inst0_data
    echo "inst0"
    if [[ "$bm" == dt.* ]]; then
        
        mpirun -np $NUM_PROCS bin/$bm BH
    fi
    if [[ "$CONFIG" == "eight-core-def" ]]; then
        numactl --physcpubind=0,1,2,3,4,5,6,7 --membind=0 -- mpirun -np $NUM_PROCS bin/$bm || numactl --physcpubind=0,1,2,3,4,5,6,7 --membind=0 -- mpirun bin/$bm
    else
        mpirun -np $NUM_PROCS bin/$bm 
    fi
    export PAPI_EVENTS="PAPI_SR_INS,PAPI_BR_INS,PAPI_VEC_INS"
    export PAPI_OUTPUT_DIRECTORY=${PWD}/../data/${MACHINE}-${CONFIG}-${SUFFIX}/npb_mpi/$bm/inst1_data
    echo "inst1"
    if [[ "$bm" == dt.* ]]; then
        
        mpirun -np $NUM_PROCS bin/$bm BH
    fi
    if [[ "$CONFIG" == "eight-core-def" ]]; then
        numactl --physcpubind=0,1,2,3,4,5,6,7 --membind=0 -- mpirun -np $NUM_PROCS bin/$bm || numactl --physcpubind=0,1,2,3,4,5,6,7 --membind=0 -- mpirun bin/$bm
    else
        mpirun -np $NUM_PROCS bin/$bm 
    fi
    export PAPI_EVENTS="PAPI_STL_ICY,PAPI_STL_CCY,PAPI_BR_MSP,PAPI_BR_PRC,PAPI_RES_STL,PAPI_TOT_CYC,PAPI_LST_INS"
    export PAPI_OUTPUT_DIRECTORY=${PWD}/../data/${MACHINE}-${CONFIG}-${SUFFIX}/npb_mpi/$bm/pipe0_data
    echo "pipe0"
    if [[ "$bm" == dt.* ]]; then
        
        mpirun -np $NUM_PROCS bin/$bm BH
    fi
    if [[ "$CONFIG" == "eight-core-def" ]]; then
        numactl --physcpubind=0,1,2,3,4,5,6,7 --membind=0 -- mpirun -np $NUM_PROCS bin/$bm || numactl --physcpubind=0,1,2,3,4,5,6,7 --membind=0 -- mpirun bin/$bm
    else
        mpirun -np $NUM_PROCS bin/$bm 
    fi
    export PAPI_EVENTS="PAPI_SYC_INS,PAPI_FP_OPS,PAPI_REF_CYC"
    export PAPI_OUTPUT_DIRECTORY=${PWD}/../data/${MACHINE}-${CONFIG}-${SUFFIX}/npb_mpi/$bm/pipe1_data
    echo "pipe1"
    if [[ "$bm" == dt.* ]]; then
        
        mpirun -np $NUM_PROCS bin/$bm BH
    fi
    if [[ "$CONFIG" == "eight-core-def" ]]; then
        numactl --physcpubind=0,1,2,3,4,5,6,7 --membind=0 -- mpirun -np $NUM_PROCS bin/$bm || numactl --physcpubind=0,1,2,3,4,5,6,7 --membind=0 -- mpirun bin/$bm
    else
        mpirun -np $NUM_PROCS bin/$bm 
    fi
done
