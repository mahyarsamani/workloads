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
cmake ../src -DCMAKE_BUILD_TYPE=Release -DCMAKE_ANNOTATE_TYPE=gem5fs
make
cd ..
cd ..

cd UME
mkdir build
cd build
cmake ../ -DCMAKE_BUILD_TYPE=Release -DUSE_CATCH2=off -DUSE_MPI=true -DCMAKE_ANNOTATE_TYPE=gem5fs -DCMAKE_ROI_TYPE=sync
make
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
cd tgv
./remake_partitioned_files.sh
./delete_partitions.sh
./extract_files.sh
./delete_compressed_files.sh
cd ..
cd ..
cd ..

cd hpcg
./configure Linux_MPI_gem5fs
make
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
