#!/bin/bash
# Fetch the SuiteSparse matrices of the SE SpMV workloads into
# se-inputs/matrices/ (git-ignored) and convert each to the binary CSR file
# that `spmv csr <file>` reads, with se-bin/host/mtx2csr
# (scripts/build-se-kernels.sh builds it), so that a simulation loads the
# matrix instead of parsing text.
#   SNAP/soc-LiveJournal1: social network, 4.8M rows, 69M nonzeros, power-law
#                          degrees (pattern: values 1.0);
#   Janna/Queen_4147:      3D finite-element structural problem, 4.1M rows,
#                          317M nonzeros once its symmetric half is mirrored.
# Either gathers x[col[k]] from a vector of about 32-39 MiB, the size of the
# system cache.
#
# Usage (from workloads/): scripts/make-se-matrices.sh
set -e

WORKLOADS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MTX2CSR="$WORKLOADS_DIR/se-bin/host/mtx2csr"
MATRICES="$WORKLOADS_DIR/se-inputs/matrices"
URL="https://suitesparse-collection-website.herokuapp.com/MM"

if [ ! -x "$MTX2CSR" ]; then
    echo "Build mtx2csr first: scripts/build-se-kernels.sh" >&2
    exit 1
fi
mkdir -p "$MATRICES/download" "$MATRICES/extracted"

for matrix in SNAP/soc-LiveJournal1 Janna/Queen_4147; do
    name="$(basename "$matrix")"
    out="$MATRICES/$name.csr"
    if [ -f "$out" ]; then
        echo "$out exists; skipping."
        continue
    fi
    archive="$MATRICES/download/$name.tar.gz"
    if [ ! -f "$archive" ]; then
        echo "### Downloading $matrix"
        curl -sSfL -o "$archive.tmp" "$URL/$matrix.tar.gz"
        mv "$archive.tmp" "$archive"
    fi
    if [ ! -f "$MATRICES/extracted/$name/$name.mtx" ]; then
        tar -xzf "$archive" -C "$MATRICES/extracted" \
            --no-same-owner --no-same-permissions
    fi
    echo "### Converting $name"
    "$MTX2CSR" "$MATRICES/extracted/$name/$name.mtx" "$out.tmp"
    mv "$out.tmp" "$out"
done
ls -la "$MATRICES"
