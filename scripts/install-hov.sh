#!/bin/bash

# Copyright (c) 2024 The Regents of the University of California.
# SPDX-License-Identifier: BSD 3-Clause

# Build and install the HOV userspace library.
#
# The hov_drv.ko kernel module is PRE-BUILT and bundled in
# modules/u2204/files/5.15.167/gem5/hov_drv.ko because the Packer VM
# does not have the 5.15.167 kernel headers needed to compile it.
# To update the driver, cross-compile it on a machine with the headers
# and replace the pre-built .ko file.

set -e

echo "=== Installing HOV ==="

NPROC=$(nproc)
HOV_DIR="/home/gem5/workloads/hov"

# ---- Build the HOV userspace library ----
echo "Building HOV library..."
pushd "${HOV_DIR}"
make -j${NPROC} lib HOV_DEBUG=1
popd

echo "=== HOV installation complete ==="
