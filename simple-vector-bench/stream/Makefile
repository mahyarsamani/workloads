CC?=gcc
CXX?=g++
CFLAGS=-O3 -fopenmp
CXXFLAGS=-O3 -fopenmp
BIN_DIR=bin

ANNOTATE_DIR=$(PWD)/../../annotate

EXT=
ifeq ($(EXTENSION), sve)
	CFLAGS+=-march=armv8.1-a+sve
	EXT="-sve"
endif

all: papi gem5 native

make_dir:
	mkdir -p $(BIN_DIR)

kernels: make_dir
	$(CC) -c -o $(BIN_DIR)/kernels.o stream_kernels.c $(CFLAGS) -Iinclude

papi: kernels
	$(CXX) -o $(BIN_DIR)/stream$(EXT).papi stream.cpp $(BIN_DIR)/kernels.o $(CXXFLAGS) -Iinclude -I$(ANNOTATE_DIR)/include -I$(ANNOTATE_DIR)/papi/install/include -L$(ANNOTATE_DIR)/lib -L$(ANNOTATE_DIR)/papi/install/lib -lannotate.papi -lpapi -lpthread

gem5fs: kernels
	$(CXX) -o $(BIN_DIR)/stream$(EXT).gem5fs stream.cpp $(BIN_DIR)/kernels.o $(CXXFLAGS) -Iinclude -I$(ANNOTATE_DIR)/include -I$(ANNOTATE_DIR)/gem5/include -L$(ANNOTATE_DIR)/lib -L$(ANNOTATE_DIR)/gem5/lib -lannotate.gem5fs -lm5

native: kernels
	$(CXX) -o $(BIN_DIR)/stream$(EXT).native stream.cpp $(BIN_DIR)/kernels.o $(CXXFLAGS) -Iinclude -I$(ANNOTATE_DIR)/include -L$(ANNOTATE_DIR)/lib -lannotate.native

clean:
	rm -f $(BIN_DIR)/stream.papi $(BIN_DIR)/stream-sve.papi
	rm -f $(BIN_DIR)/stream.gem5fs $(BIN_DIR)/stream-sve.gem5fs
	rm -f $(BIN_DIR)/stream.native $(BIN_DIR)/stream-sve.native
	rm -f $(BIN_DIR)/kernels.o
