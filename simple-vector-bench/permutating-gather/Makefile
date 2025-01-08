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
	$(CC) -c -o $(BIN_DIR)/gather-kernel.o gather_kernel.c $(CFLAGS) -Iinclude

papi: kernels
	$(CXX) -o $(BIN_DIR)/permutating-gather$(EXT).papi permutating_gather.cpp $(BIN_DIR)/gather-kernel.o $(CXXFLAGS) -Iinclude -I$(ANNOTATE_DIR)/include -I$(ANNOTATE_DIR)/papi/install/include -L$(ANNOTATE_DIR)/lib -L$(ANNOTATE_DIR)/papi/install/lib -lannotate.papi -lpapi -lpthread

gem5fs: kernels
	$(CXX) -o $(BIN_DIR)/permutating-gather$(EXT).gem5fs permutating_gather.cpp $(BIN_DIR)/gather-kernel.o $(CXXFLAGS) -Iinclude -I$(ANNOTATE_DIR)/include -I$(ANNOTATE_DIR)/gem5/include -L$(ANNOTATE_DIR)/lib -L$(ANNOTATE_DIR)/gem5/lib -lannotate.gem5fs -lm5

native: kernels
	$(CXX) -o $(BIN_DIR)/permutating-gather$(EXT).native permutating_gather.cpp $(BIN_DIR)/gather-kernel.o $(CXXFLAGS) -Iinclude -I$(ANNOTATE_DIR)/include -L$(ANNOTATE_DIR)/lib -lannotate.native

clean:
	rm -f $(BIN_DIR)/permutating-gather.papi $(BIN_DIR)/permutating-gather-sve.papi
	rm -f $(BIN_DIR)/permutating-gather.gem5fs $(BIN_DIR)/permutating-gather-sve.gem5fs
	rm -f $(BIN_DIR)/permutating-gather.native $(BIN_DIR)/permutating-gather-sve.native
	rm -f $(BIN_DIR)/gather-kernel.o
