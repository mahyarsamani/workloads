#include "include/annotate.h"

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

void annotate_term_()
{}

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

void annotate_term_()
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

#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

void annotate_init_()
{
    map_m5_mem();

    pid_t pid = getpid();
    const char *dir = getenv("PID_DUMP_PATH");
    if (!dir || !*dir) {
        fprintf(
            stderr, "[pid-dump] env var PID_DUMP_PATH is not set — skipping dump\n"
        );
        return;
    }

    if (mkdir(dir, 0755) == -1 && errno != EEXIST) {
        fprintf(
            stderr, "[pid-dump] cannot create directory '%s': %s\n",
            dir, strerror(errno)
        );
        return;
    }

    char path[PATH_MAX];
    int n = snprintf(path, sizeof(path), "%s/pid_%d", dir, (int) pid);
    if (n < 0 || n >= (int) sizeof(path)) {
        fprintf(stderr, "[pid-dump] resulting path is too long\n");
        return;
    }

    FILE *fp = fopen(path, "w");
    if (!fp) {
        fprintf(stderr,
                "[pid-dump] cannot open '%s' for writing: %s\n",
                path, strerror(errno));
        return;
    }
    fclose(fp);

    fprintf(stderr, "[pid-dump] wrote %s\n", path);

    const char *done_file = getenv("MMAP_DONE_PATH");
    if (!done_file) {
        return;
    }

    char val[8] = {0};

    while (1) {
        fp = fopen(done_file, "r");
        if (fp) {
            if (fgets(val, sizeof(val), fp)) {
                if (strncmp(val, "1", 1) == 0) {
                    fclose(fp);
                    break;
                }
            }
            fclose(fp);
        }
        usleep(62500);
    }
}

void annotate_term_()
{
    unmap_m5_mem();
}

void region_begin_(const char* region)
{}

void region_end_(const char* region)
{}

void roi_begin_()
{
    m5_work_begin_addr(0, 0);
}

void roi_end_()
{
    m5_work_end_addr(0,0);
}

void thread_init_()
{}

#else
#include <stdio.h>

void annotate_init_()
{}

void annotate_term_()
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
