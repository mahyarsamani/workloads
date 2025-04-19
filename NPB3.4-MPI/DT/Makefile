SHELL=/bin/sh
BENCHMARK=dt
BENCHMARKU=DT

include ../config/make.def

include ../sys/make.common
CMPI_LIB += $(ROI_LIB)
CMPI_LIB += $(ROI_OBJ)
CMPI_INC += $(ROI_INC)

#Override PROGRAM
DTPROGRAM  = $(BINDIR)/$(BENCHMARK).$(CLASS).x

OBJS = dt.o DGraph.o \
	${COMMON}/c_print_results.o ${COMMON}/c_timers.o ${COMMON}/c_randdp.o


${PROGRAM}: config ${OBJS}
	${CLINK} ${CLINKFLAGS} -o ${DTPROGRAM} ${OBJS} ${ROI_BIN} ${CMPI_LIB} 

.c.o:
	${CCOMPILE} $<

dt.o:             dt.c  npbparams.h
DGraph.o:	DGraph.c DGraph.h

clean:
	- rm -f *.o *~ mputil*
	- rm -f dt npbparams.h core
