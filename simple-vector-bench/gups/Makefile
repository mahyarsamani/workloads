CC?=gcc
CXX?=g++
CFLAGS=-O2 -fopenmp
CXXFLAGS=-O2 -fopenmp
BIN_DIR=bin
ANNOTATE_DIR=$(PWD)/../../annotate

EXT=
ifeq ($(EXTENSION), sve)
	CFLAGS+=-march=armv8.1-a+sve
	EXT="-sve"
endif

all: papi gem5fs native

make_dir:
	mkdir -p $(BIN_DIR)

kernels: make_dir
	$(CC) -c -o $(BIN_DIR)/kernels.o gups_kernels.c $(CFLAGS) -Iinclude

papi: kernels
	$(CXX) -o $(BIN_DIR)/gups$(EXT).papi gups.cpp $(BIN_DIR)/kernels.o $(CXXFLAGS) -Iinclude -I$(ANNOTATE_DIR)/include -I$(ANNOTATE_DIR)/papi/install/include -L$(ANNOTATE_DIR)/lib -L$(ANNOTATE_DIR)/papi/install/lib -lannotate.papi -lpapi -lpthread

gem5fs: kernels
	$(CXX) -o $(BIN_DIR)/gups$(EXT).gem5fs gups.cpp $(BIN_DIR)/kernels.o $(CXXFLAGS) -Iinclude -I$(ANNOTATE_DIR)/include -I$(ANNOTATE_DIR)/gem5/include -L$(ANNOTATE_DIR)/lib -L$(ANNOTATE_DIR)/gem5/lib -lannotate.gem5fs -lm5

native: kernels
	$(CXX) -o $(BIN_DIR)/gups$(EXT).native gups.cpp $(BIN_DIR)/kernels.o $(CXXFLAGS) -Iinclude -I$(ANNOTATE_DIR)/include -L$(ANNOTATE_DIR)/lib -lannotate.native

clean:
	rm -f bin/gups.papi bin/gups-sve.papi
	rm -f bin/gups.gem5fs bin/gups-sve.gem5fs
	rm -f bin/gups.native bin/gups-sve.native
	rm -f bin/kernels.o
