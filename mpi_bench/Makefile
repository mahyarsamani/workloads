CXX       := mpic++
OPTFLAGS  := -O3
SVE_FLAGS  := -DUSE_SVE -march=armv8.6-a+sve -msve-vector-bits=512

ANNOTATE_FLAGS := -DANNOTATE -DSYNC_ON_ROI
ANNOTATE_DIR := $(PWD)/../annotate
ANNOTATE_LIB := -L$(ANNOTATE_DIR)/lib
ANNOTATE_INC := -I$(ANNOTATE_DIR)/include
GEM5_ANNOTATE_LIB := -L$(ANNOTATE_DIR)/gem5/lib -lannotate.gem5fs -lm5
PAPI_ANNOTATE_LIB := -L$(ANNOTATE_DIR)/papi/install/lib -lannotate.papi -lpapi -lpthread

SRC   := mpi_bench.cc
BINARY_BASE := mpi_bench
ASM_BASE := asm_mpi_bench


all: native gem5 papi

native:
	@echo "Building binaries with no annotations."
	$(CXX) $(OPTFLAGS) -o $(BINARY_BASE) $(SRC)
	$(CXX) $(OPTFLAGS) -fverbose-asm -S -o $(ASM_BASE) $(SRC)
	$(CXX) $(OPTFLAGS) $(SVE_FLAGS) -o $(BINARY_BASE)_sve $(SRC)
	$(CXX) $(OPTFLAGS) $(SVE_FLAGS) -fverbose-asm -S -o $(ASM_BASE)_sve $(SRC)

gem5:
	@echo "Building binaries with gem5 annotations."
	$(CXX) $(ANNOTATE_FLAGS) $(ANNOTATE_INC) $(ANNOTATE_LIB) $(GEM5_ANNOTATE_LIB) $(OPTFLAGS) -o $(BINARY_BASE)_gem5 $(SRC)
	$(CXX) $(ANNOTATE_FLAGS) $(ANNOTATE_INC) $(ANNOTATE_LIB) $(GEM5_ANNOTATE_LIB) $(OPTFLAGS) -fverbose-asm -S -o $(ASM_BASE)_gem5 $(SRC)
	$(CXX) $(ANNOTATE_FLAGS) $(ANNOTATE_INC) $(ANNOTATE_LIB) $(GEM5_ANNOTATE_LIB) $(OPTFLAGS) $(SVE_FLAGS) -o $(BINARY_BASE)_gem5_sve $(SRC)
	$(CXX) $(ANNOTATE_FLAGS) $(ANNOTATE_INC) $(ANNOTATE_LIB) $(GEM5_ANNOTATE_LIB) $(OPTFLAGS) $(SVE_FLAGS) -fverbose-asm -S -o $(ASM_BASE)_gem5_sve $(SRC)

papi:
	@echo "Building binaries with papi annotations."
	$(CXX) $(ANNOTATE_FLAGS) $(ANNOTATE_INC) $(ANNOTATE_LIB) $(PAPI_ANNOTATE_LIB) $(OPTFLAGS) -o $(BINARY_BASE)_papi $(SRC)
	$(CXX) $(ANNOTATE_FLAGS) $(ANNOTATE_INC) $(ANNOTATE_LIB) $(PAPI_ANNOTATE_LIB) $(OPTFLAGS) -fverbose-asm -S -o $(ASM_BASE)_papi $(SRC)
	$(CXX) $(ANNOTATE_FLAGS) $(ANNOTATE_INC) $(ANNOTATE_LIB) $(PAPI_ANNOTATE_LIB) $(OPTFLAGS) $(SVE_FLAGS) -o $(BINARY_BASE)_papi_sve $(SRC)
	$(CXX) $(ANNOTATE_FLAGS) $(ANNOTATE_INC) $(ANNOTATE_LIB) $(PAPI_ANNOTATE_LIB) $(OPTFLAGS) $(SVE_FLAGS) -fverbose-asm -S -o $(ASM_BASE)_papi_sve $(SRC)


clean:
	rm -f mpi_bench mpi_bench_sve asm_mpi_bench asm_mpi_bench_sve
	rm -f mpi_bench_gem5 mpi_bench_gem5_sve asm_mpi_bench_gem5 asm_mpi_bench_gem5_sve
	rm -f mpi_bench_papi mpi_bench_papi_sve asm_mpi_bench_papi asm_mpi_bench_papi_sve
