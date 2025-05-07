SHELL=/bin/sh
BENCHMARK=mg
BENCHMARKU=MG
F08=def

include ../config/make.def

OBJS = mg.o mg_data.o mpinpb.o ${COMMON}/print_results.o  \
       ${COMMON}/get_active_nprocs.o \
       ${COMMON}/${RAND}.o ${COMMON}/timers.o

include ../sys/make.common
FMPI_LIB += $(ROI_LIB)
FMPI_LIB += $(ROI_OBJ)
FMPI_INC += $(ROI_INC)

${PROGRAM}: config ${OBJS}
	${FLINK} ${FLINKFLAGS} -o ${PROGRAM} ${OBJS} ${ROI_BIN} ${FMPI_LIB}

.f90.o:
	${FCOMPILE} $<

mg.o:		mg.f90  mg_data.o mpinpb.o
mg_data.o:	mg_data.f90 mpinpb.o npbparams.h
mpinpb.o:	mpinpb.f90
mpinpb.f90:     mpinpb_$(F08).f90
	cp mpinpb_$(F08).f90 $@

clean:
	- rm -f *.o *.mod *~ 
	- rm -f npbparams.h core mpinpb.f90



