SHELL=/bin/sh
CLASS=U
SUBTYPE=
VERSION=
F08=def
MFLAGS=CLASS=$(CLASS) F08=$(F08)
SFILE=config/suite.def

ROI_DIR=$(PWD)/../annotate
ROI_BIN=
ROI_OBJ=
ROI_INC=-I$(ROI_DIR)/include
ROI_LIB=

ifeq ($(PLATFORM), papi)
	ROI_BIN+=$(ROI_DIR)/lib/libannotate.papi.so
	ROI_INC+=-I$(ROI_DIR)/papi/install/include
	ROI_LIB+=-L$(ROI_DIR)/papi/install/lib
	ROI_OBJ+=-lpapi
	ROI_OBJ+=-lpthread
else ifeq ($(PLATFORM), gem5)
	ROI_BIN+=$(ROI_DIR)/lib/libannotate.gem5fs.so
	ROI_INC+=-I$(ROI_DIR)/gem5/include
	ROI_LIB+=-L$(ROI_DIR)/gem5/lib
	ROI_OBJ+=-lm5
else
	ROI_BIN+=$(ROI_DIR)/lib/libannotate.native.so
endif

default: header
	@ sys/print_instructions

make_dir:
	mkdir -p bin

BT: bt make_dir
bt: header
	cd BT; $(MAKE) $(MFLAGS) SUBTYPE=$(SUBTYPE) VERSION=$(VERSION)

SP: sp make_dir
sp: header
	cd SP; $(MAKE) $(MFLAGS)

LU: lu make_dir
lu: header
	cd LU; $(MAKE) $(MFLAGS) VERSION=$(VERSION)

MG: mg make_dir
mg: header
	cd MG; $(MAKE) $(MFLAGS)

FT: ft make_dir
ft: header
	cd FT; $(MAKE) $(MFLAGS)

IS: is make_dir
is: header
	cd IS; $(MAKE) $(MFLAGS)

CG: cg make_dir
cg: header
	cd CG; $(MAKE) $(MFLAGS)

EP: ep make_dir
ep: header
	cd EP; $(MAKE) $(MFLAGS)

DT: dt make_dir
dt: header
	cd DT; $(MAKE) $(MFLAGS)

# Awk script courtesy cmg@cray.com, modified by Haoqiang Jin
suite:
	@ awk -f sys/suite.awk SMAKE=$(MAKE) $(SFILE) | $(SHELL)


# It would be nice to make clean in each subdirectory (the targets
# are defined) but on a really clean system this will won't work
# because those makefiles need config/make.def
clean:
	- rm -f core *~ */core */*~
	- rm -f */*.o */*.mod */*.obj */*.exe */npbparams.h */mpinpb.*
	- rm -f MPI_dummy/test MPI_dummy/libmpi.a
	- rm -f sys/setparams sys/makesuite sys/setparams.h
	- rm -f btio.*.out*

veryclean: clean
	- rm -f config/make.def config/suite.def 
	- rm -f bin/sp.* bin/lu.* bin/mg.* bin/ft.* bin/bt.* bin/is.* 
	- rm -f bin/ep.* bin/cg.* bin/dt.*

header:
	@ sys/print_header

