# ==== Toolchain / Target ====
TRIPLE  ?= aarch64-linux-gnu
CC       = $(TRIPLE)-gcc

# ==== Sysroot ====
SYSROOT ?= /home/mahyar/scratch/sysroots/aarch64
ifneq ($(strip $(SYSROOT)),)
  SYSROOT_CFLAGS  := --sysroot=$(SYSROOT)
  SYSROOT_LDFLAGS := --sysroot=$(SYSROOT)
endif

# ==== Paths (relative to workloads/hov/) ====
HOV_ROOT    := ../../..
HOV_INC     := $(HOV_ROOT)/include
HOV_LIB     := $(HOV_ROOT)/lib

# ==== Flags ====
CFLAGS  := -Wall -Wextra -O2 -I$(HOV_INC) $(SYSROOT_CFLAGS)
LDFLAGS := -L$(HOV_LIB) $(SYSROOT_LDFLAGS)

# ==== Sources / Outputs ====
SRC     := test_load.c
BINARY  := test_load

# ============================================================================
# Targets
# ============================================================================

.PHONY: all clean

all: $(BINARY)

$(BINARY): $(SRC) $(HOV_LIB)/libhov.a
	$(CC) $(CFLAGS) -o $@ $< $(HOV_LIB)/libhov.a $(LDFLAGS)

clean:
	rm -f $(BINARY)
