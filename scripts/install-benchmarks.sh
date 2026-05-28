#!/bin/bash

# Copyright (c) 2024 The Regents of the University of California.
# SPDX-License-Identifier: BSD 3-Clause

cd $HOME

cd workloads

cd annotate/
make gem5fs
cd ..

cd mpi_bench
make gem5
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
cmake ../src -DCMAKE_BUILD_TYPE=Release -DCMAKE_ANNOTATE_TYPE=gem5fs -DSYNC_ANNOTATE=true -DCMAKE_CXX_FLAGS="-DROI_BRANSON"
make
mv BRANSON BRANSON_ref

# Build HOV Variant
make clean
cmake ../src -DCMAKE_BUILD_TYPE=Release -DCMAKE_ANNOTATE_TYPE=gem5fs -DSYNC_ANNOTATE=true -DCMAKE_CXX_FLAGS="-DHOV -DROI_BRANSON -I../../hov/include" -DCMAKE_EXE_LINKER_FLAGS="-L../../hov/lib -lhov"
make
mv BRANSON BRANSON_hov
cd ..
cd ..

cd UME
mkdir build
cd build
# Build Reference Variants
cmake ../ -DCMAKE_BUILD_TYPE=Release -DUSE_CATCH2=off -DUSE_MPI=true -DCMAKE_ANNOTATE_TYPE=gem5fs -DCMAKE_ROI_TYPE=sync
make
mv src/ume_mpi_gradzatz src/ume_mpi_gradzatz_ref
mv src/ume_mpi_gradzatz_invert src/ume_mpi_gradzatz_invert_ref
mv src/ume_mpi_face_area src/ume_mpi_face_area_ref

# Build HOV Variants
make clean
cmake ../ -DCMAKE_BUILD_TYPE=Release -DUSE_CATCH2=off -DUSE_MPI=true -DCMAKE_ANNOTATE_TYPE=gem5fs -DCMAKE_ROI_TYPE=sync -DCMAKE_CXX_FLAGS="-DHOV -I../../hov/include" -DCMAKE_EXE_LINKER_FLAGS="-L../../hov/lib -lhov"
make
mv src/ume_mpi_gradzatz src/ume_mpi_gradzatz_hov
mv src/ume_mpi_gradzatz_invert src/ume_mpi_gradzatz_invert_hov
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

cd hov
make lib
cd ..

cd hpcg
./configure Linux_MPI_gem5fs_sync
for kernel in SPMVM SYMGS WAXPBY MG CG; do
    # Build Reference Variant
    make clean
    make EXTRA_CXXFLAGS="-DROI_$kernel"
    mv bin/xhpcg bin/xhpcg_${kernel,,}_ref_gem5fs

    # Build HOV Variant (only truly impacts SPMVM and SYMGS, but we'll build all for consistency)
    make clean
    make EXTRA_CXXFLAGS="-DROI_$kernel -DHOV" EXTRA_LINKFLAGS="-L../hov/lib -lhov"
    mv bin/xhpcg bin/xhpcg_${kernel,,}_hov_gem5fs
done
cd ..

cd simple-vector-bench

cd gups
make gem5fs
make gem5fs EXTENSION=sve
cd ..

cd permutating-gather
make gem5fs
make gem5fs EXTENSION=sve
cd ..

cd permutating-scatter
make gem5fs
make gem5fs EXTENSION=sve
cd ..

cd spatter
make gem5fs
make gem5fs EXTENSION=sve
cd ..
cd ..
cd spatter-traces
./remake_partitioned_files.sh
cd ..

cd simple-vector-bench/stream
make gem5fs
make gem5fs EXTENSION=sve
cd ..
cd ..
