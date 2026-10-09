#!/bin/bash

# Copyright (c) 2024 The Regents of the University of California.
# SPDX-License-Identifier: BSD 3-Clause

# Benchmarks of the ref disk image (packer variable variant=ref): the
# reference (non-SIFT) builds only. The hov builds are in
# install-benchmarks-hov.sh, which builds the hov image.

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

pushd NPB3.4-OMP
./build_npb_gem5.sh
popd

pushd NPB3.4-MPI
./build_npb_gem5.sh
popd

pushd branson
mkdir -p build
pushd build
# Branson is ref-only: the hov (SIFT) variant is parked on the branson
# sift-hov branch (see SIFT_HOV_NOTES.md there).
cmake ../src -DCMAKE_BUILD_TYPE=Release -DANNOTATE_TOOL=gem5fs -DROI_TYPE=sync
make -j$NPROC
mv BRANSON BRANSON_ref
popd
popd

pushd UME
mkdir -p build
pushd build
cmake ../ -DCMAKE_BUILD_TYPE=Release -DUSE_CATCH2=off -DUSE_MPI=true -DANNOTATE_TOOL=gem5fs -DROI_TYPE=sync -DHOV=OFF
make -j$NPROC
mv src/ume_mpi_gradzatz src/ume_mpi_gradzatz_ref
mv src/ume_mpi_gradzatp src/ume_mpi_gradzatp_ref
mv src/ume_mpi_gradzatz_invert src/ume_mpi_gradzatz_invert_ref
mv src/ume_mpi_gradzatp_invert src/ume_mpi_gradzatp_invert_ref
mv src/ume_mpi_face_area src/ume_mpi_face_area_ref
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
    make clean arch=Linux_MPI_gem5fs
    make -j$NPROC arch=Linux_MPI_gem5fs HPCG_KERNEL=$kernel
    mv bin/xhpcg bin/xhpcg_${kernel,,}_ref_gem5fs
done
popd

pushd simple-vector-bench
pushd gups
make -j$NPROC gem5fs
make -j$NPROC gem5fs EXTENSION=sve
popd

pushd permutating-gather
make -j$NPROC gem5fs
make -j$NPROC gem5fs EXTENSION=sve
popd

pushd permutating-scatter
make -j$NPROC gem5fs
make -j$NPROC gem5fs EXTENSION=sve
popd

pushd spatter
make -j$NPROC gem5fs
make -j$NPROC gem5fs EXTENSION=sve
popd
popd

pushd spatter-traces
./remake_partitioned_files.sh
popd

pushd simple-vector-bench/stream
make -j$NPROC gem5fs
make -j$NPROC gem5fs EXTENSION=sve
popd
