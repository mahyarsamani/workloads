# ==== Toolchain / Target ====
TRIPLE ?= aarch64-linux-gnu
CC      = $(TRIPLE)-gcc
AR      = $(TRIPLE)-ar

# ==== Sysroot ====
HOST_ARCH := $(shell uname -m)
ifneq ($(MAKECMDGOALS),clean)
ifeq ($(strip $(SYSROOT)),)
  ifneq ($(HOST_ARCH),aarch64)
    $(error "Error: SYSROOT is not defined and host architecture is $(HOST_ARCH). Cross-compilation requires SYSROOT to be set")
  endif
endif
endif


ifneq ($(strip $(SYSROOT)),)
  SYSROOT_CFLAGS := --sysroot=$(SYSROOT)
  SYSROOT_INC := -I$(SYSROOT)/usr/local/include
else
  SYSROOT_INC := -I/usr/local/include
endif

# ==== Flags ====
CFLAGS := -Wall -O2 -fPIC $(SYSROOT_CFLAGS) $(SYSROOT_INC)

# ==== Directories ====
LIB_DIR     := lib
PAPI_INC    := papi/install/include
INC_DIR     := include

# ==== Source ====
SRC := annotate.c

# ============================================================================
# Targets
# ============================================================================

.PHONY: all gem5se gem5fs papi native clean

all: gem5se gem5fs papi native clean

# ---- gem5 SE mode ----
gem5se: $(LIB_DIR)/libannotate.gem5se.a $(LIB_DIR)/libannotate.gem5se.so

$(LIB_DIR)/libannotate.gem5se.a: $(SRC) | $(LIB_DIR)
	$(CC) $(CFLAGS) -DGEM5SE -c $< -o $@

$(LIB_DIR)/libannotate.gem5se.so: $(SRC) | $(LIB_DIR)
	$(CC) $(CFLAGS) -DGEM5SE -shared -o $@ $<

# ---- gem5 FS mode ----
gem5fs: $(LIB_DIR)/libannotate.gem5fs.a $(LIB_DIR)/libannotate.gem5fs.so

$(LIB_DIR)/libannotate.gem5fs.a: $(SRC) | $(LIB_DIR)
	$(CC) $(CFLAGS) -DGEM5FS -c $< -o $@

$(LIB_DIR)/libannotate.gem5fs.so: $(SRC) | $(LIB_DIR)
	$(CC) $(CFLAGS) -DGEM5FS -shared -o $@ $<

# ---- PAPI ----
papi: $(LIB_DIR)/libannotate.papi.a $(LIB_DIR)/libannotate.papi.so

$(LIB_DIR)/libannotate.papi.a: $(SRC) | $(LIB_DIR)
	$(CC) $(CFLAGS) -DPAPI -I$(PAPI_INC) -c $< -o $@

$(LIB_DIR)/libannotate.papi.so: $(SRC) | $(LIB_DIR)
	$(CC) $(CFLAGS) -DPAPI -I$(PAPI_INC) -shared -o $@ $<

# ---- Native (no instrumentation) ----
native: $(LIB_DIR)/libannotate.native.a $(LIB_DIR)/libannotate.native.so

$(LIB_DIR)/libannotate.native.a: $(SRC) | $(LIB_DIR)
	$(CC) $(CFLAGS) -c $< -o $@

$(LIB_DIR)/libannotate.native.so: $(SRC) | $(LIB_DIR)
	$(CC) $(CFLAGS) -shared -o $@ $<

# ---- Directory ----
$(LIB_DIR):
	mkdir -p $(LIB_DIR)

# ---- Clean ----
clean:
	rm -f $(LIB_DIR)/libannotate.*.a $(LIB_DIR)/libannotate.*.so
