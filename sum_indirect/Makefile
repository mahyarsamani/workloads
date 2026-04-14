# ==== Toolchain / Target ====
# Override on the command line as needed:
#   make CXX=g++ TRIPLE= SYSROOT=            # native host build
#   make CXX=aarch64-linux-gnu-g++           # cross (uses default TRIPLE below)
TRIPLE ?= aarch64-linux-gnu
CXX    ?= $(TRIPLE)-g++
CC     ?= $(TRIPLE)-gcc

# Optional: use Clang as a cross-compiler
#   make CXX=clang++ CLANG=1
ifdef CLANG
TARGET_FLAG := --target=$(TRIPLE)
endif

# ==== Sysroot (optional) ====
# Point this at the sysroot you built: e.g. SYSROOT=$$HOME/sysroots/aarch64
SYSROOT ?=
ifneq ($(strip $(SYSROOT)),)
  SYSROOT_CFLAGS  := --sysroot=$(SYSROOT)
  # Help the linker find transitive deps inside the sysroot
  SYSROOT_LDFLAGS := --sysroot=$(SYSROOT) \
                     -Wl,-rpath-link,$(SYSROOT)/lib \
                     -Wl,-rpath-link,$(SYSROOT)/lib/$(TRIPLE) \
                     -Wl,-rpath-link,$(SYSROOT)/usr/lib \
                     -Wl,-rpath-link,$(SYSROOT)/usr/lib/$(TRIPLE) \
                     -Wl,-rpath-link,$(SYSROOT)/lib/aarch64-linux-gnu \
                     -Wl,-rpath-link,$(SYSROOT)/usr/lib/aarch64-linux-gnu
endif

# ==== Optimization & ISA flags ====
OPTFLAGS   := -O3
# Only apply SVE flags when targeting AArch64 toolchains
ifneq (,$(findstring aarch64,$(TRIPLE)))
  SVE_FLAGS := -DUSE_SVE -march=armv8.6-a+sve -msve-vector-bits=512
endif

# ==== Annotation libs/incs (as you had) ====
ANNOTATE_FLAGS := -DANNOTATE
ANNOTATE_DIR   := $(PWD)/../annotate
ANNOTATE_LIB   := -L$(ANNOTATE_DIR)/lib
ANNOTATE_INC   := -I$(ANNOTATE_DIR)/include
GEM5_ANNOTATE_LIB  := -L$(ANNOTATE_DIR)/gem5/lib -lannotate.gem5se -lm5
PAPI_ANNOTATE_LIB  := -L$(ANNOTATE_DIR)/papi/install/lib -lannotate.papi -lpapi -lpthread

# ==== Sources / Outputs ====
SRC         := sum_indirect.cc
BINARY_BASE := sum_indirect
ASM_BASE    := asm_sum_indirect

# ==== Common flags ====
CXXWARN   := -Wall -Wextra -Wno-unused-parameter
CXXSTD    := -std=c++17
CXXBASE   := $(TARGET_FLAG) $(OPTFLAGS) $(CXXSTD) $(CXXWARN) $(SYSROOT_CFLAGS)
LDFLAGS   := $(SYSROOT_LDFLAGS)
ASMFLAGS  := -fverbose-asm -S

# ==== Helpers (compile & assemble) ====
# $1=name suffix, $2=extra cxxflags, $3=extra ldlibs
define build_bin_and_asm
$(BINARY_BASE)$1: $(SRC)
	$(CXX) $(CXXBASE) $(ANNOTATE_INC) $(2) -o $$@ $$< $(LDFLAGS) $(ANNOTATE_LIB) $(3)
$(ASM_BASE)$1: $(SRC)
	$(CXX) $(CXXBASE) $(ANNOTATE_INC) $(2) $(ASMFLAGS) -o $$@ $$<
endef

.PHONY: all native gem5 papi clean print-config

all: native gem5 papi

print-config:
	@echo "CXX            = $(CXX)"
	@echo "TRIPLE         = $(TRIPLE)"
	@echo "SYSROOT        = $(SYSROOT)"
	@echo "CXXBASE        = $(CXXBASE)"
	@echo "LDFLAGS        = $(LDFLAGS)"
	@echo "SVE_FLAGS      = $(SVE_FLAGS)"

# ---- native (no annotations) ----
$(eval $(call build_bin_and_asm,,$(EMPTY),$(EMPTY)))
ifneq ($(strip $(SVE_FLAGS)),)
  $(eval $(call build_bin_and_asm,_sve,$(SVE_FLAGS),$(EMPTY)))
endif

native: $(BINARY_BASE) $(ASM_BASE) $(if $(SVE_FLAGS),$(BINARY_BASE)_sve $(ASM_BASE)_sve,)

# ---- gem5 annotations ----
$(eval $(call build_bin_and_asm,_gem5,$(ANNOTATE_FLAGS),$(GEM5_ANNOTATE_LIB)))
ifneq ($(strip $(SVE_FLAGS)),)
  $(eval $(call build_bin_and_asm,_gem5_sve,$(ANNOTATE_FLAGS) $(SVE_FLAGS),$(GEM5_ANNOTATE_LIB)))
endif

gem5: $(BINARY_BASE)_gem5 $(ASM_BASE)_gem5 $(if $(SVE_FLAGS),$(BINARY_BASE)_gem5_sve $(ASM_BASE)_gem5_sve,)

# ---- papi annotations ----
$(eval $(call build_bin_and_asm,_papi,$(ANNOTATE_FLAGS),$(PAPI_ANNOTATE_LIB)))
ifneq ($(strip $(SVE_FLAGS)),)
  $(eval $(call build_bin_and_asm,_papi_sve,$(ANNOTATE_FLAGS) $(SVE_FLAGS),$(PAPI_ANNOTATE_LIB)))
endif

papi: $(BINARY_BASE)_papi $(ASM_BASE)_papi $(if $(SVE_FLAGS),$(BINARY_BASE)_papi_sve $(ASM_BASE)_papi_sve,)

# ---- clean ----
clean:
	rm -f $(BINARY_BASE) $(BINARY_BASE)_sve $(ASM_BASE) $(ASM_BASE)_sve
	rm -f $(BINARY_BASE)_gem5 $(BINARY_BASE)_gem5_sve $(ASM_BASE)_gem5 $(ASM_BASE)_gem5_sve
	rm -f $(BINARY_BASE)_papi $(BINARY_BASE)_papi_sve $(ASM_BASE)_papi $(ASM_BASE)_papi_sve