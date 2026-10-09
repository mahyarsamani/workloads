#!/bin/bash

# Copyright (c) 2024 The Regents of the University of California.
# SPDX-License-Identifier: BSD 3-Clause

# Benchmarks of the hov disk image (packer variable variant=hov): the SIFT
# (hov) builds only, linked against libhov, which install-hov.sh builds
# first. The reference builds are in install-benchmarks-ref.sh.

# Stop on the first failing build, so packer reports it instead of
# producing an image with missing binaries.
set -e

cd $HOME

# Number of parallel jobs for make
NPROC=$(nproc)

cd workloads

pushd annotate/
make -j$NPROC gem5fs
popd

pushd UME
mkdir -p build
pushd build
cmake ../ -DCMAKE_BUILD_TYPE=Release -DUSE_CATCH2=off -DUSE_MPI=true -DANNOTATE_TOOL=gem5fs -DROI_TYPE=sync -DHOV=ON
make -j$NPROC
mv src/ume_mpi_gradzatz src/ume_mpi_gradzatz_hov
mv src/ume_mpi_gradzatp src/ume_mpi_gradzatp_hov
mv src/ume_mpi_gradzatz_invert src/ume_mpi_gradzatz_invert_hov
mv src/ume_mpi_gradzatp_invert src/ume_mpi_gradzatp_invert_hov
mv src/ume_mpi_face_area src/ume_mpi_face_area_hov
popd

pushd inputs/blake
./remake_partitioned_files.sh
./delete_partitions.sh
./extract_files.sh
./delete_compressed_files.sh
popd

pushd inputs/pipe_3d
./remake_partitioned_files.sh
./delete_partitions.sh
./extract_files.sh
./delete_compressed_files.sh
popd

# scale_mesh is built by every UME configuration, HOV=ON included.
mpirun -np 8 ./build/src/scale_mesh inputs/pipe_3d/pipe_3d/pipe_3d_00001 2
mpirun -np 8 ./build/src/scale_mesh inputs/pipe_3d/pipe_3d/pipe_3d_00001 4
mpirun -np 1 ./build/src/scale_mesh inputs/blake/blake/blake 128
popd

pushd hpcg
# In-source configure: its last step copies setup/Make.<arch> onto itself,
# which fails with status 1 after the Makefile has been generated. Ignore
# only that; real configure errors (missing arch/setup file) exit 127.
./configure Linux_MPI_gem5fs || [ $? -eq 1 ]
for kernel in SPMVM SYMGS WAXPBY MG CG; do
    make clean arch=Linux_MPI_gem5fs_hov
    make -j$NPROC arch=Linux_MPI_gem5fs_hov HPCG_KERNEL=$kernel
    mv bin/xhpcg bin/xhpcg_${kernel,,}_hov_gem5fs
done
popd
