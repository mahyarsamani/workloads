#!/bin/bash
# Generate the inputs of the SE kernels into se-inputs/ (git-ignored):
# gapbs graphs as serialized .sg files, made on the host with
# se-bin/host/converter (scripts/build-se-kernels.sh builds it), so that a
# simulation loads the graph instead of building it.
#   uniform (-u): every vertex's neighbours are uniformly random (DX100's
#                 choice; the least locality);
#   kron (-g):    Kronecker (Graph500) graphs, skewed degrees, so the hubs'
#                 data caches well.
# Average degree 16 (gapbs's default).
#
# Usage (from workloads/): scripts/make-se-inputs.sh [scale ...]
# (default scales: 20 22); OMP_NUM_THREADS bounds the converter's threads.
set -e

WORKLOADS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONVERTER="$WORKLOADS_DIR/se-bin/host/converter"
GRAPHS="$WORKLOADS_DIR/se-inputs/graphs"
SCALES=("${@:-20 22}")
# shellcheck disable=SC2206
SCALES=(${SCALES[*]})

if [ ! -x "$CONVERTER" ]; then
    echo "Build the converter first: scripts/build-se-kernels.sh" >&2
    exit 1
fi
mkdir -p "$GRAPHS"

for scale in "${SCALES[@]}"; do
    for kind in uniform kron; do
        flag="-u"
        [ "$kind" = kron ] && flag="-g"
        out="$GRAPHS/$kind-$scale.sg"
        if [ -f "$out" ]; then
            echo "$out exists; skipping."
            continue
        fi
        echo "### $kind, scale $scale"
        "$CONVERTER" "$flag" "$scale" -b "$out.tmp"
        mv "$out.tmp" "$out"
    done
done
ls -la "$GRAPHS"
