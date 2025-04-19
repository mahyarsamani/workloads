SHELL=/bin/sh
BENCHMARK=ep
BENCHMARKU=EP
F08=def

include ../config/make.def

OBJS = ep.o ep_data.o verify.o mpinpb.o \
	${COMMON}/print_results.o ${COMMON}/${RAND}.o ${COMMON}/timers.o

include ../sys/make.common
FMPI_LIB += $(ROI_LIB)
FMPI_LIB += $(ROI_OBJ)
FMPI_INC += $(ROI_INC)

${PROGRAM}: config ${OBJS}
	${FLINK} ${FLINKFLAGS} -o ${PROGRAM} ${OBJS} ${ROI_BIN} ${FMPI_LIB}

.f90.o:
	${FCOMPILE} $<

ep.o:		ep.f90 ep_data.o mpinpb.o
ep_data.o:	ep_data.f90 npbparams.h
verify.o:	verify.f90
mpinpb.o:	mpinpb.f90
mpinpb.f90:     mpinpb_$(F08).f90
	cp mpinpb_$(F08).f90 $@

clean:
	- rm -f *.o *~ *.mod
	- rm -f npbparams.h core mpinpb.f90



