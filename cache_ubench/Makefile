# configure based on h/w specs
L1_SIZE_BYTES=65536
L2_SIZE_BYTES=1048576
L3_SIZE_BYTES=33554432
ITERS_PER_TEST=2048

CXX=g++
ROI_DIR=$(PWD)/../annotate
CXXFLAGS=-O3
TYPE_INT=-DINT
TYPE_FP=-DFP
CXXFLAGS_ASM=-S -fverbose-asm
CXXFLAGS_ANNOTATE=-DANNOTATE
CXXFLAGS_GEM5=$(CXXFLAGS_ANNOTATE) -I$(ROI_DIR)/include -I$(ROI_DIR)/gem5/include -L$(ROI_DIR)/lib -L$(ROI_DIR)/gem5/lib -lannotate.gem5se -lm5
CXXFLAGS_PAPI=$(CXXFLAGS_ANNOTATE) -I$(ROI_DIR)/include -I$(ROI_DIR)/papi/install/include -L$(ROI_DIR)/lib -L$(ROI_DIR)/papi/install/lib -lannotate.papi -lpapi -lpthread
USER_DEFINES=-DL1_SIZE_BYTES=$(L1_SIZE_BYTES) -DL2_SIZE_BYTES=$(L2_SIZE_BYTES) -DL3_SIZE_BYTES=$(L3_SIZE_BYTES) -DITERS_PER_TEST=$(ITERS_PER_TEST)



all: cache_ubench.int.native cache_ubench.fp.native cache_ubench.int.native.asm cache_ubench.fp.native.asm cache_ubench.int.papi cache_ubench.fp.papi cache_ubench.int.papi.asm cache_ubench.fp.papi.asm cache_ubench.int.gem5 cache_ubench.fp.gem5 cache_ubench.int.gem5.asm cache_ubench.fp.gem5.asm

int: cache_ubench.int.native cache_ubench.int.native.asm cache_ubench.int.papi cache_ubench.int.papi.asm cache_ubench.int.gem5 cache_ubench.int.gem5.asm
fp: cache_ubench.fp.native cache_ubench.fp.native.asm cache_ubench.fp.papi cache_ubench.fp.papi.asm cache_ubench.fp.gem5 cache_ubench.fp.gem5.asm

native: cache_bench.int.native cache_bench.fp.native cache_bench.int.native.asm cache_bench.fp.native.asm
papi: cache_ubench.int.papi cache_ubench.fp.papi cache_ubench.int.papi.asm cache_ubench.fp.papi.asm
gem5: cache_ubench.int.gem5 cache_ubench.fp.gem5 cache_ubench.int.gem5.asm cache_ubench.fp.gem5.asm

bin: cache_ubench.int.native cache_ubench.fp.native cache_ubench.int.papi cache_ubench.fp.papi cache_ubench.int.gem5 cache_ubench.fp.gem5
asm: cache_ubench.int.native.asm cache_ubench.fp.native.asm cache_ubench.int.papi.asm cache_ubench.fp.papi.asm cache_ubench.int.gem5.asm cache_ubench.fp.gem5.asm

%.int.native: %.cpp
	$(CXX) $< -o $@ $(TYPE_INT) $(USER_DEFINES) $(CXXFLAGS)
%.fp.native: %.cpp
	$(CXX) $< -o $@ $(TYPE_FP) $(USER_DEFINES) $(CXXFLAGS)
%.int.native.asm: %.cpp
	$(CXX) $< -o $@ $(TYPE_INT) $(USER_DEFINES) $(CXXFLAGS) $(CXXFLAGS_ASM)
%.fp.native.asm: %.cpp
	$(CXX) $< -o $@ $(TYPE_FP) $(USER_DEFINES) $(CXXFLAGS) $(CXXFLAGS_ASM)

%.int.papi: %.cpp
	$(CXX) $< -o $@ $(TYPE_INT) $(USER_DEFINES) $(CXXFLAGS_PAPI)
%.fp.papi: %.cpp
	$(CXX) $< -o $@ $(TYPE_FP) $(USER_DEFINES) $(CXXFLAGS_PAPI)
%.int.papi.asm: %.cpp
	$(CXX) $< -o $@ $(TYPE_INT) $(USER_DEFINES) $(CXXFLAGS_PAPI) $(CXXFLAGS_ASM)
%.fp.papi.asm: %.cpp
	$(CXX) $< -o $@ $(TYPE_FP) $(USER_DEFINES) $(CXXFLAGS_PAPI) $(CXXFLAGS_ASM)

%.int.gem5: %.cpp
	$(CXX) $< -o $@ $(TYPE_INT) $(USER_DEFINES) $(CXXFLAGS_GEM5)
%.fp.gem5: %.cpp
	$(CXX) $< -o $@ $(TYPE_FP) $(USER_DEFINES) $(CXXFLAGS_GEM5)
%.int.gem5.asm: %.cpp
	$(CXX) $< -o $@ $(TYPE_INT) $(USER_DEFINES) $(CXXFLAGS_GEM5) $(CXXFLAGS_ASM)
%.fp.gem5.asm: %.cpp
	$(CXX) $< -o $@ $(TYPE_FP) $(USER_DEFINES) $(CXXFLAGS_GEM5) $(CXXFLAGS_ASM)

clean:
	rm -f cache_bench.int.native cache_bench.fp.native cache_bench.int.native.asm cache_bench.fp.native.asm
	rm -f cache_ubench.int.papi cache_ubench.fp.papi cache_ubench.int.papi.asm cache_ubench.fp.papi.asm
	rm -f cache_ubench.int.gem5 cache_ubench.fp.gem5 cache_ubench.int.gem5.asm cache_ubench.fp.gem5.asm
