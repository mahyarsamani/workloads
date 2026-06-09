#!/bin/bash

# Copyright (c) 2024 The Regents of the University of California.
# SPDX-License-Identifier: BSD 3-Clause

# This script verifies that all workloads successfully cross-compile to aarch64.
# It performs the compilation in an isolated temporary directory to avoid
# polluting the main repository with object files and binaries.

# 1. Detect architecture mismatch and sysroot
HOST_ARCH=$(uname -m)
if [ "$HOST_ARCH" != "aarch64" ]; then
    if [ -z "$SYSROOT" ]; then
        echo "Error: Host architecture is $HOST_ARCH but SYSROOT is not set."
        echo "Cross-compilation requires SYSROOT to be set to the path of your aarch64 sysroot."
        exit 1
    fi
fi

# Make SYSROOT absolute if set
if [ -n "$SYSROOT" ]; then
    export SYSROOT=$(readlink -f "$SYSROOT")
fi

# 2. Set up temporary directory
TEMP_DIR=$(mktemp -d -t workloads_build_XXXXXX)
echo "Building in temporary directory: $TEMP_DIR"

cleanup() {
    echo "========================================"
    echo "Cleaning up mounts and temporary directory..."
    if [ -n "$SYSROOT" ]; then
        sudo umount -l "$SYSROOT/dev/pts" 2>/dev/null || true
        sudo umount -l "$SYSROOT/dev" 2>/dev/null || true
        sudo umount -l "$SYSROOT/sys" 2>/dev/null || true
        sudo umount -l "$SYSROOT/proc" 2>/dev/null || true
        sudo umount -l "$SYSROOT$TEMP_DIR" 2>/dev/null || true
    fi
    rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

# Bind mount the temporary directory and filesystems into the sysroot
if [ -n "$SYSROOT" ]; then
    sudo mkdir -p "$SYSROOT$TEMP_DIR"
    sudo mount --bind "$TEMP_DIR" "$SYSROOT$TEMP_DIR"
    sudo mount -t proc /proc "$SYSROOT/proc"
    sudo mount -t sysfs /sys "$SYSROOT/sys"
    sudo mount -o bind /dev "$SYSROOT/dev"
    sudo mount -o bind /dev/pts "$SYSROOT/dev/pts"
fi

ORIG_DIR=$(pwd)
# Copy source files to temp directory, excluding massive disk images and datasets
rsync -a --exclude="arm-*" \
         --exclude="checkpoints" \
         --exclude="data" \
         --exclude="inputs" \
         --exclude="spatter-traces" \
         --exclude="modules" \
         --exclude="files" \
         --exclude="packer" \
         --exclude="*.img" \
         --exclude=".git" \
         --exclude="sysroots" \
         "$(dirname "$0")/" "$TEMP_DIR/workloads/"

# Keep logs in the original workloads directory
LOG_DIR=$ORIG_DIR/compilation_logs
mkdir -p "$LOG_DIR"
echo "Logs will be written to: $LOG_DIR"

cd "$TEMP_DIR/workloads"

# Keep track of successes and failures
SUCCESSES=()
FAILURES=()

# Function to run and log a build step
run_build() {
    local name=$1
    local cmd=$2
    local log_file="$LOG_DIR/${name}.log"
    echo "========================================"
    echo "Building $name..."
    echo "Command: $cmd"
    echo "Log: $log_file"

    # We execute the command natively inside the sysroot using chroot.
    # We redirect both stdout and stderr to the log file.
    # We also tee it to the console so the user can see progress.
    sudo chroot "$SYSROOT" /bin/bash -c "cd $TEMP_DIR/workloads && $cmd" 2>&1 | tee "$log_file"

    if [ ${PIPESTATUS[0]} -eq 0 ]; then
        echo "[SUCCESS] $name"
        SUCCESSES+=("$name")
    else
        echo "[FAILED] $name (See $log_file)"
        FAILURES+=("$name")
    fi
}

# 3. Resilient Execution (set +e is the default, but we enforce it conceptually by manually handling exit codes)
set +e

# Number of parallel jobs for make
NPROC=$(nproc)

# --- Annotate ---
run_build "annotate" "cd annotate && make -j$NPROC gem5fs"

# --- HOV ---
run_build "hov" "cd hov && make -j$NPROC lib"


# # --- NPB3.4-OMP ---
run_build "NPB3.4-OMP" "cd NPB3.4-OMP && ./build_npb_gem5.sh"

# # --- NPB3.4-MPI ---
run_build "NPB3.4-MPI" "cd NPB3.4-MPI && ./build_npb_gem5.sh"

# --- Branson ---
run_build "branson" "cd branson && mkdir build && cd build && \
    cmake ../src -DCMAKE_BUILD_TYPE=Release -DANNOTATE_TOOL=gem5fs -DROI_TYPE=sync && \
    make -j$NPROC && \
    make clean && \
    cmake ../src -DCMAKE_BUILD_TYPE=Release -DANNOTATE_TOOL=gem5fs -DROI_TYPE=sync -DHOV=ON && \
    make -j$NPROC"

# --- UME ---
run_build "UME" "cd UME && mkdir build && cd build && \
    cmake ../ -DCMAKE_BUILD_TYPE=Release -DUSE_CATCH2=off -DUSE_MPI=true -DANNOTATE_TOOL=gem5fs -DROI_TYPE=sync && \
    make -j$NPROC && \
    make clean && \
    cmake ../ -DCMAKE_BUILD_TYPE=Release -DUSE_CATCH2=off -DUSE_MPI=true -DANNOTATE_TOOL=gem5fs -DROI_TYPE=sync -DHOV=ON && \
    make -j$NPROC"


# --- HPCG ---
run_build "hpcg" "cd hpcg && (./configure Linux_MPI_gem5fs || true) && \
    for kernel in SPMVM SYMGS WAXPBY MG CG; do \
        make clean arch=Linux_MPI_gem5fs && \
        make -j$NPROC arch=Linux_MPI_gem5fs HPCG_KERNEL=\$kernel && \
        make clean arch=Linux_MPI_gem5fs_hov && \
        make -j$NPROC arch=Linux_MPI_gem5fs_hov HPCG_KERNEL=\$kernel; \
    done"

# --- Simple Vector Bench ---
run_build "simple-vector-bench" "cd simple-vector-bench && \
    cd gups && make gem5fs && make gem5fs EXTENSION=sve && cd .. && \
    cd permutating-gather && make gem5fs && make gem5fs EXTENSION=sve && cd .. && \
    cd permutating-scatter && make gem5fs && make gem5fs EXTENSION=sve && cd .. && \
    cd spatter && make gem5fs && make gem5fs EXTENSION=sve && cd .. && \
    cd stream && make gem5fs && make gem5fs EXTENSION=sve"

# 4. Cleanup
# Handled by trap

# 5. Summary
echo "========================================"
echo "CROSS-COMPILATION SUMMARY"
echo "========================================"
echo "Successful Builds (${#SUCCESSES[@]}):"
for name in "${SUCCESSES[@]}"; do
    echo "  - $name"
done

if [ ${#FAILURES[@]} -gt 0 ]; then
    echo "Failed Builds (${#FAILURES[@]}):"
    for name in "${FAILURES[@]}"; do
        echo "  - $name"
    done
    exit 1
else
    echo "All builds succeeded!"
    exit 0
fi
