#!/bin/bash

# Copyright (c) 2024 The Regents of the University of California.
# SPDX-License-Identifier: BSD 3-Clause

cd $HOME

cd workloads

mpicc -o mpi_hello_world mpi_hello_world.c

cd annotate/
make gem5fs
cd ..

cd NPB3.4-OMP
./build_npb_gem5.sh
cd ..

cd branson
mkdir build
cd build
cmake ../src -DCMAKE_BUILD_TYPE=Release -DCMAKE_ANNOTATE_TYPE=gem5fs
make
cd ../..

cd UME
mkdir build
cd build
cmake .. -DUSE_CATCH2=off -DUSE_MPI=true -DCMAKE_ANNOTATE_TYPE=gem5fs
make
cd ..
cd inputs
./remake_partitioned_files.sh
tar -xJvf pipe_3d.tar.xz
rm pipe_3d.tar.xz
rm pipe_3d.tar.xz.part.000
rm pipe_3d.tar.xz.part.001
rm pipe_3d.tar.xz.part.002
mkdir blake
tar -xzvf ume1r.tar.gz -C blake
cd ../..

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
cd ../..
cd spatter-traces
./remake_partitioned_files.sh
cd ..

cd simple-vector-bench/stream
make gem5fs
make gem5fs EXTENSION=sve
cd ../..
