// Two threads share an array, to check how CBU is sampled when coherence
// invalidates blocks (gem5 CacheMemory invalidatedUsefulBytes) and what a
// shared cache records across cores.
//
// Region of interest, three phases separated by barriers:
//   1. thread 0 reads every byte of `shared` (its blocks are fully used);
//   2. thread 1 writes every element, invalidating thread 0's copies;
//   3. both threads read every element again.
// Expected at thread 0's core: one invalidated sample per block of `shared`
// at the L1D, each with all 64 bytes used.
//
// Usage: share_inval [bytes] (default 32768, which fits a 64 KiB L1D);
// run with OMP_NUM_THREADS=2.

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
    size_t n = bytes / sizeof(double);
    std::vector<double> shared(n);
    for (size_t i = 0; i < n; i++)
        shared[i] = (double)i;
    double sums[2] = {0.0, 0.0};

#ifdef ANNOTATE
    roi_begin_();
#endif
#pragma omp parallel num_threads(2)
    {
        int t = omp_get_thread_num();
        if (t == 0) {
            double sum = 0.0;
            for (size_t i = 0; i < n; i++)
                sum += shared[i];
            sums[0] = sum;
        }
#pragma omp barrier
        if (t == 1) {
            for (size_t i = 0; i < n; i++)
                shared[i] = shared[i] + 1.0;
        }
#pragma omp barrier
        double sum = 0.0;
        for (size_t i = 0; i < n; i++)
            sum += shared[i];
        sums[t] += sum;
    }
#ifdef ANNOTATE
    roi_end_();
#endif

    // Thread 0: sum(i) + sum(i + 1); thread 1: sum(i + 1).
    double base = (double)n * (double)(n - 1) / 2.0;
    bool ok = sums[0] == 2.0 * base + (double)n && sums[1] == base + (double)n;
    printf("%zu bytes, sums %.1f %.1f\nVerification: %s\n", bytes, sums[0],
           sums[1], ok ? "PASS" : "FAIL");
    return ok ? 0 : 1;
}
