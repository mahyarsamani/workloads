// Two threads share every cache line of an array but never the same
// bytes, to check gem5's snoop-sharing counters (CacheMemory
// snoop{False,True}Sharing{Shared,Unique}): every snoop that moves a line
// between the two cores here is false sharing.
//
// Each 64-byte line holds 8 doubles; thread 0 owns elements 0-3 of every
// line, thread 1 elements 4-7. Region of interest, rounds separated by
// barriers:
//   1. writes, `rounds` times: thread 0 writes its half of every line,
//      then thread 1 writes its half; each write takes the line from the
//      other core, whose copy only used the other half (false, unique);
//   2. reads after a write: thread 0 writes its half, then thread 1 reads
//      its half, which thread 0's modified copy never touched (false,
//      shared).
// Expected at each core's L1D: about `rounds` unique false-sharing snoops
// per line, about one shared false-sharing snoop per line at thread 0's
// core, and no true sharing on `shared`.
//
// Usage: share_false [bytes] [rounds] (defaults 32768 and 4; 32 KiB fits
// a 64 KiB L1D); run with OMP_NUM_THREADS=2.

#include <cstdio>
#include <cstdlib>
#include <vector>

#include <omp.h>

#ifdef ANNOTATE
extern "C" {
#include "annotate.h"
}
#endif

int main(int argc, char **argv) {
    size_t bytes = argc > 1 ? std::strtoul(argv[1], nullptr, 0) : 32768;
    int rounds = argc > 2 ? std::atoi(argv[2]) : 4;
    const size_t per_line = 64 / sizeof(double);
    const size_t half = per_line / 2;
    size_t lines = bytes / 64;
    // 64-byte aligned, so element k * 8 starts a line.
    double *shared = static_cast<double *>(
        std::aligned_alloc(64, lines * 64));
    for (size_t i = 0; i < lines * per_line; i++)
        shared[i] = 0.0;
    double sum1 = 0.0;

#ifdef ANNOTATE
    roi_begin_();
#endif
#pragma omp parallel num_threads(2)
    {
        int t = omp_get_thread_num();
        size_t first = t == 0 ? 0 : half;
        for (int r = 0; r < rounds; r++) {
            if (t == 0) {
                for (size_t l = 0; l < lines; l++)
                    for (size_t e = first; e < first + half; e++)
                        shared[l * per_line + e] += 1.0;
            }
#pragma omp barrier
            if (t == 1) {
                for (size_t l = 0; l < lines; l++)
                    for (size_t e = first; e < first + half; e++)
                        shared[l * per_line + e] += 1.0;
            }
#pragma omp barrier
        }
        if (t == 0) {
            for (size_t l = 0; l < lines; l++)
                for (size_t e = first; e < first + half; e++)
                    shared[l * per_line + e] += 1.0;
        }
#pragma omp barrier
        if (t == 1) {
            double sum = 0.0;
            for (size_t l = 0; l < lines; l++)
                for (size_t e = first; e < first + half; e++)
                    sum += shared[l * per_line + e];
            sum1 = sum;
        }
    }
#ifdef ANNOTATE
    roi_end_();
#endif

    // Thread 1's half was incremented `rounds` times per element.
    double expected = (double)rounds * (double)(lines * half);
    bool ok = sum1 == expected;
    printf("%zu bytes, %d rounds, sum %.1f\nVerification: %s\n",
           lines * 64, rounds, sum1, ok ? "PASS" : "FAIL");
    std::free(shared);
    return ok ? 0 : 1;
}
