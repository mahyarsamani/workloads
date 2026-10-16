#!/bin/bash
# Build the SE-mode OpenMP kernels (gapbs, NPB-CPP CG, SpMV, UME-kernels) for
# aarch64 with the sysroot in sysroots/aarch64, dynamically linked.
#
# The compiler is the sysroot's own gcc-13, run through qemu-user with the
# sysroot as its file-system prefix (QEMU_LD_PREFIX) and its own binutils
# (-B): headers, libraries and compiler all come from the sysroot, as in
# the disk images. (Ubuntu's aarch64 cross gcc searches its own glibc
# headers before --sysroot's, so its binaries need a newer glibc than the
# sysroot has.)
#
# Two flavours, in se-bin/<flavour>/:
# - gem5se: region of interest marked with gem5 work begin/end
#   (workloads/annotate built with -DGEM5SE, and the sysroot's libm5.a),
#   for gem5;
# - native: the same markers as no-ops, to run and verify under
#   qemu-aarch64-static (gem5's m5 instructions are illegal there).
# Also builds two host tools that make the inputs: gapbs's converter (graphs)
# and SpMV's mtx2csr (SuiteSparse matrices).
#
# Usage (from workloads/): scripts/build-se-kernels.sh [gem5se|native ...]
set -e

WORKLOADS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SYSROOT="$(realpath "$WORKLOADS_DIR/sysroots/aarch64")"
ANNOTATE_DIR="$WORKLOADS_DIR/annotate"
OUT_DIR="$WORKLOADS_DIR/se-bin"
FLAVOURS=("${@:-gem5se native gem5se-hov}")
# shellcheck disable=SC2206
FLAVOURS=(${FLAVOURS[*]})
NPB_CLASSES="S B C D"

if [ ! -x "$SYSROOT/usr/bin/g++-13" ]; then
    echo "No usable sysroot at $SYSROOT (see create_arm_sysroot.sh)." >&2
    exit 1
fi

# NOTE: Paths inside the sysroot (/usr/include, /usr/local/lib) are seen
# through the prefix; host paths such as this repository are not in the
# sysroot, so qemu passes them through unchanged.
QEMU="env QEMU_LD_PREFIX=$SYSROOT qemu-aarch64-static"
CC="$QEMU $SYSROOT/usr/bin/gcc-13 -B$SYSROOT/usr/bin/"
CXX="$QEMU $SYSROOT/usr/bin/g++-13 -B$SYSROOT/usr/bin/"
CXXFLAGS="-O3 -fopenmp -I$ANNOTATE_DIR/include"

for flavour in "${FLAVOURS[@]}"; do
    out="$OUT_DIR/$flavour"
    mkdir -p "$out/gapbs" "$out/npb" "$out/ume"
    # NOTE: HOV adds the SIFT variants' flag (each kernel's region of
    # interest issues ldind; its warm-up runs the ref code); KERNELS_GAPBS
    # leaves BFS out of them (its accesses are a frontier bitmap and
    # compare-and-swap, not data[index[j]]).
    HOV=""
    KERNELS_GAPBS="pr pr_spmv bfs"
    case "$flavour" in
    gem5se)
        $CC -O2 -DGEM5SE -c "$ANNOTATE_DIR/annotate.c" -o "$out/annotate.o"
        LIBS="$out/annotate.o -L/usr/local/lib -lm5"
        ;;
    native)
        $CC -O2 -c "$ANNOTATE_DIR/annotate.c" -o "$out/annotate.o"
        LIBS="$out/annotate.o"
        ;;
    gem5se-hov)
        $CC -O2 -DGEM5SE -c "$ANNOTATE_DIR/annotate.c" -o "$out/annotate.o"
        $CC -O2 -I"$WORKLOADS_DIR/hov/include" \
            -c "$WORKLOADS_DIR/hov/src/hov.c" -o "$out/hov.o"
        LIBS="$out/annotate.o $out/hov.o -L/usr/local/lib -lm5"
        HOV="-DSIFT_HOV -I$WORKLOADS_DIR/hov/include"
        KERNELS_GAPBS="pr pr_spmv"
        ;;
    *) echo "Unknown flavour $flavour (gem5se, native, gem5se-hov)." >&2; exit 1 ;;
    esac

    echo "### gapbs ($flavour)"
    # NOTE: PR and pr_spmv mark two iterations (warm-up, ROI); BFS marks
    # two trials (-DANNOTATE_TRIALS; run with -n 2).
    for kernel in $KERNELS_GAPBS; do
        trials=""
        [ "$kernel" = bfs ] && trials="-DANNOTATE_TRIALS"
        $CXX -std=c++11 $CXXFLAGS $HOV -Wall -DANNOTATE $trials \
            "$WORKLOADS_DIR/gapbs/src/$kernel.cc" -o "$out/gapbs/$kernel" $LIBS
    done

    echo "### NPB-CPP CG ($flavour)"
    npb="$WORKLOADS_DIR/NPB-CPP/NPB-OMP"
    for class in $NPB_CLASSES; do
        # NOTE: The objects are built in the source tree, so clean before
        # each flavour and class; setparams runs on the host (UCC).
        rm -f "$npb"/common/*.o "$npb"/CG/*.o
        make -C "$npb/CG" CLASS="$class" BINDIR="$out/npb" \
            CC="$CXX -std=c++14" CLINK="$CXX -std=c++14" \
            CFLAGS="$CXXFLAGS $HOV -DANNOTATE" CLINKFLAGS="-O3 -fopenmp" \
            C_LIB="-lm $LIBS" UCC="g++ -fopenmp" >/dev/null
    done
    rm -f "$npb"/common/*.o "$npb"/CG/*.o "$npb"/CG/npbparams.hpp

    echo "### SpMV ($flavour)"
    mkdir -p "$out/spmv"
    $CXX -std=c++14 $CXXFLAGS $HOV -Wall -DANNOTATE \
        "$WORKLOADS_DIR/spmv/spmv.cpp" -o "$out/spmv/spmv" $LIBS

    if [ -z "$HOV" ]; then
        echo "### se-tests ($flavour)"
        mkdir -p "$out/se-tests"
        for test in share_inval share_false; do
            $CXX -std=c++17 $CXXFLAGS -Wall -DANNOTATE \
                "$WORKLOADS_DIR/se-tests/$test.cpp" \
                -o "$out/se-tests/$test" $LIBS
        done
    fi

    echo "### UME-kernels ($flavour)"
    for kernel in gradzatz gradzatz_invert gradzatp_invert gradzatp; do
        $CXX -std=c++11 $CXXFLAGS $HOV -DSIFT \
            "$WORKLOADS_DIR/UME-kernels/$kernel.cpp" -o "$out/ume/$kernel" $LIBS
    done
done

echo "### gapbs converter (host)"
mkdir -p "$OUT_DIR/host"
g++ -std=c++11 -O3 -fopenmp "$WORKLOADS_DIR/gapbs/src/converter.cc" \
    -o "$OUT_DIR/host/converter"

echo "### SpMV mtx2csr (host)"
g++ -std=c++14 -O3 -Wall "$WORKLOADS_DIR/spmv/mtx2csr.cpp" \
    -o "$OUT_DIR/host/mtx2csr"

echo "Built into $OUT_DIR."
