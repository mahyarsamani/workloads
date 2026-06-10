#!/bin/bash

# Copyright (c) 2024 The Regents of the University of California.
# SPDX-License-Identifier: BSD 3-Clause

cd $HOME

# Number of parallel jobs for make
NPROC=$(nproc)

cd workloads

cd annotate/
make -j$NPROC gem5fs
cd ..

cd hov
make -j$NPROC lib
cd ..

cd NPB3.4-OMP
./build_npb_gem5.sh
cd ..

cd NPB3.4-MPI
./build_npb_gem5.sh
cd ..

cd branson
mkdir build
cd build
# Build Reference Variant
cmake ../src -DCMAKE_BUILD_TYPE=Release -DANNOTATE_TOOL=gem5fs -DROI_TYPE=sync
make -j$NPROC
mv BRANSON BRANSON_ref

# Build HOV Variant
make clean
cmake ../src -DCMAKE_BUILD_TYPE=Release -DANNOTATE_TOOL=gem5fs -DROI_TYPE=sync -DHOV=ON
make -j$NPROC
mv BRANSON BRANSON_hov
cd ..
cd ..

cd UME
mkdir build
cd build
# Build Reference Variants
cmake ../ -DCMAKE_BUILD_TYPE=Release -DUSE_CATCH2=off -DUSE_MPI=true -DANNOTATE_TOOL=gem5fs -DROI_TYPE=sync
make -j$NPROC
mv src/ume_mpi_gradzatz src/ume_mpi_gradzatz_ref
mv src/ume_mpi_gradzatp src/ume_mpi_gradzatp_ref
mv src/ume_mpi_gradzatz_invert src/ume_mpi_gradzatz_invert_ref
mv src/ume_mpi_gradzatp_invert src/ume_mpi_gradzatp_invert_ref
mv src/ume_mpi_face_area src/ume_mpi_face_area_ref

# Build HOV Variants
make clean
cmake ../ -DCMAKE_BUILD_TYPE=Release -DUSE_CATCH2=off -DUSE_MPI=true -DANNOTATE_TOOL=gem5fs -DROI_TYPE=sync -DHOV=ON
make -j$NPROC
mv src/ume_mpi_gradzatz src/ume_mpi_gradzatz_hov
mv src/ume_mpi_gradzatp src/ume_mpi_gradzatp_hov
mv src/ume_mpi_gradzatz_invert src/ume_mpi_gradzatz_invert_hov
mv src/ume_mpi_gradzatp_invert src/ume_mpi_gradzatp_invert_hov
mv src/ume_mpi_face_area src/ume_mpi_face_area_hov
cd ..
cd inputs
cd blake
./remake_partitioned_files.sh
./delete_partitions.sh
./extract_files.sh
./delete_compressed_files.sh
cd ..
cd pipe_3d
./remake_partitioned_files.sh
./delete_partitions.sh
./extract_files.sh
./delete_compressed_files.sh
cd ..
cd ..
mpirun -np 8 ./build/src/scale_mesh inputs/pipe_3d/pipe_3d/pipe_3d_00001 2
mpirun -np 8 ./build/src/scale_mesh inputs/pipe_3d/pipe_3d/pipe_3d_00001 4
mpirun -np 1 ./build/src/scale_mesh inputs/blake/blake/blake 128
cd ..

cd hpcg
./configure Linux_MPI_gem5fs
for kernel in SPMVM SYMGS WAXPBY MG CG; do
    # Build Reference Variant
    make clean arch=Linux_MPI_gem5fs
    make -j$NPROC arch=Linux_MPI_gem5fs HPCG_KERNEL=$kernel
    mv bin/xhpcg bin/xhpcg_${kernel,,}_ref_gem5fs

    # Build HOV Variant (only truly impacts SPMVM and SYMGS, but we'll build all for consistency)
    make clean arch=Linux_MPI_gem5fs_hov
    make -j$NPROC arch=Linux_MPI_gem5fs_hov HPCG_KERNEL=$kernel
    mv bin/xhpcg bin/xhpcg_${kernel,,}_hov_gem5fs
done
cd ..

cd simple-vector-bench

cd gups
make -j$NPROC gem5fs
make -j$NPROC gem5fs EXTENSION=sve
cd ..

cd permutating-gather
make -j$NPROC gem5fs
make -j$NPROC gem5fs EXTENSION=sve
cd ..

cd permutating-scatter
make -j$NPROC gem5fs
make -j$NPROC gem5fs EXTENSION=sve
cd ..

cd spatter
make -j$NPROC gem5fs
make -j$NPROC gem5fs EXTENSION=sve
cd ..
cd ..
cd spatter-traces
./remake_partitioned_files.sh
cd ..

cd simple-vector-bench/stream
make -j$NPROC gem5fs
make -j$NPROC gem5fs EXTENSION=sve
cd ..
cd ..
