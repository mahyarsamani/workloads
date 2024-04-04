#include "include/roi.h"

#if defined(PAPI)
#include <stdio.h>
#include <pthread.h>
#include "papi.h"

void annotate_init_()
{
    int retval = PAPI_library_init(PAPI_VER_CURRENT);
    if (retval != PAPI_VER_CURRENT) {
        printf("PAPI_library_init failed due to %d.\n", retval);
    }
}

void region_begin_(const char* region)
{
    int retval = PAPI_hl_region_begin(region);
    if (retval != PAPI_OK) {
        printf("PAPI_hl_region_begin failed due to %d.\n", retval);
    }
}

void region_end_(const char* region)
{
    int retval = PAPI_hl_region_end(region);
    if (retval != PAPI_OK) {
        printf("PAPI_hl_region_end failed due to %d.\n", retval);
    }
}

void roi_begin_()
{
    region_begin_("roi");
}

void roi_end_()
{
    region_end_("roi");
}

void thread_init_()
{
    PAPI_thread_init(pthread_self);
}

#elif defined(GEM5SE)
#include "gem5/m5ops.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

void annotate_init_()
{}

void region_begin_(const char* region)
{}

void region_end_(const char* region)
{}

void roi_begin_() {
    m5_work_begin(0, 0);
}

void roi_end_()
{
    m5_work_end(0,0);
}

void thread_init_()
{}

#elif defined(GEM5FS)
#include "gem5/m5ops.h"
#include "gem5/m5_mmap.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

void annotate_init_()
{
    char buf[256 * 1024];
    int pid = getpid();
    sprintf(buf,"cat /proc/%i/maps > proc_maps.txt;",pid);
    printf("running %s\n",buf);
    system(buf);
    printf("ready to call m5 writefile\n");
    system("m5 --addr 0x10010000 writefile proc_maps.txt;");
    printf("enable m5 address mode\n");
    m5op_addr = 0x10010000;
    map_m5_mem();
}

void region_begin_(const char* region)
{}

void region_end_(const char* region)
{}

void roi_begin_() {
    m5_work_begin_addr(0, 0);
}

void roi_end_()
{
    m5_work_end_addr(0,0);
    unmap_m5_mem();
}

void thread_init_()
{}

#else
#include <stdio.h>

void annotate_init_()
{}

void region_begin_(const char* region)
{
    printf("Reached the beginning of %s region.\n", region);
}

void region_end_(const char* region)
{
    printf("Reached the end of %s region.\n", region);
}

void roi_begin_()
{
    region_begin_("roi");
}

void roi_end_(const char* region)
{
    region_end_("roi");
}

void thread_init_()
{}

#endif // defined(PAPI)
