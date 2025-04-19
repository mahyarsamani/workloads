SHELL=/bin/sh
BENCHMARK=is
BENCHMARKU=IS

include ../config/make.def

include ../sys/make.common
CMPI_LIB += $(ROI_LIB)
CMPI_LIB += $(ROI_OBJ)
CMPI_INC += $(ROI_INC)

OBJS = is.o ${COMMON}/c_print_results.o ${COMMON}/c_timers.o


${PROGRAM}: config ${OBJS}
	${CLINK} ${CLINKFLAGS} -o ${PROGRAM} ${OBJS} ${ROI_BIN} ${CMPI_LIB}

.c.o:
	${CCOMPILE} $<

is.o:             is.c  npbparams.h


clean:
	- rm -f *.o *~ mputil*
	- rm -f is npbparams.h core
