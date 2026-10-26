// Gather microbenchmark M1 (docs/agents/2026-10-23-imp-dmp-baselines/
// SPEC.md section 5.2): sum += data[index[i]] with 4-byte indices, for
// checking an indirect prefetcher (IMP) in isolation.
//
// Every thread owns its arrays: `data` of 4 MiB (float: 1 Mi elements,
// double: 512 Ki), four times a 1 MiB L2, and `index` of `elements`
// uint32_t indices into it, uniformly random (`random`, seeded per thread)
// or i mod n (`dense`, the control: a stream the stride prefetcher covers).
// One pass over `index` is the warm-up and the next the region of
// interest, each between roi_begin_ and roi_end_ (gem5 work begin/end in
// the gem5se flavour).
//
// Usage: gather <float|double> <random|dense> [elements per thread]
//        [seed]
// (defaults 1048576 and 1); the thread count is OMP_NUM_THREADS.
// data[k] = k mod 13, exact in float and double; each thread's sum is
// checked bit for bit against the same additions, in the same order, made
// while the indices are generated.

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

#include <omp.h>

#ifdef ANNOTATE
extern "C" {
#include "annotate.h"
}
#endif

static const size_t kDataBytes = 4u << 20;

// The kernel, kept out of line so its two loads have one PC each (the
// insights snippet labels them).
template <typename T>
__attribute__((noinline)) T
gather(const T *data, const uint32_t *index, size_t elements)
{
    T sum = 0;
    for (size_t i = 0; i < elements; i++)
        sum += data[index[i]];
    return sum;
}

// xorshift64*: a small, deterministic generator per thread.
static uint64_t
next_random(uint64_t &state)
{
    state ^= state >> 12;
    state ^= state << 25;
    state ^= state >> 27;
    return state * 2685821657736338717ull;
}

template <typename T>
static int
run(bool dense, size_t elements, uint64_t seed)
{
    const size_t n = kDataBytes / sizeof(T);
    const int threads = omp_get_max_threads();
    std::vector<std::vector<T>> data(threads);
    std::vector<std::vector<uint32_t>> index(threads);
    std::vector<T> expected(threads, 0);

#pragma omp parallel
    {
        const int t = omp_get_thread_num();
        data[t].resize(n);
        for (size_t k = 0; k < n; k++)
            data[t][k] = (T)(k % 13);
        index[t].resize(elements);
        uint64_t state = (seed + 1) * 0x9e3779b97f4a7c15ull + t;
        T sum = 0;
        for (size_t i = 0; i < elements; i++) {
            uint32_t k = dense ? (uint32_t)(i % n)
                               : (uint32_t)(next_random(state) % n);
            index[t][i] = k;
            sum += (T)(k % 13);
        }
        expected[t] = sum;
    }

    std::vector<T> sums(threads, 0);
    for (int pass = 0; pass < 2; pass++) {
#ifdef ANNOTATE
        roi_begin_();
#endif
#pragma omp parallel
        {
            const int t = omp_get_thread_num();
            sums[t] = gather(data[t].data(), index[t].data(), elements);
        }
#ifdef ANNOTATE
        roi_end_();
#endif
    }

    bool ok = true;
    for (int t = 0; t < threads; t++) {
        if (sums[t] != expected[t]) {
            printf("Thread %d: sum %.1f, expected %.1f\n", t,
                   (double)sums[t], (double)expected[t]);
            ok = false;
        }
    }
    printf("%s %s, %zu elements per thread over %zu, %d threads\n",
           sizeof(T) == 4 ? "float" : "double", dense ? "dense" : "random",
           elements, n, threads);
    printf("Verification: %s\n", ok ? "PASS" : "FAIL");
    return ok ? 0 : 1;
}

static void
usage(const char *name)
{
    fprintf(stderr,
            "Usage: %s <float|double> <random|dense> [elements per thread]"
            " [seed]\n",
            name);
    exit(2);
}

int
main(int argc, char **argv)
{
    if (argc < 3)
        usage(argv[0]);
    bool is_float = strcmp(argv[1], "float") == 0;
    if (!is_float && strcmp(argv[1], "double") != 0)
        usage(argv[0]);
    bool dense = strcmp(argv[2], "dense") == 0;
    if (!dense && strcmp(argv[2], "random") != 0)
        usage(argv[0]);
    size_t elements = argc > 3 ? strtoull(argv[3], nullptr, 0) : 1u << 20;
    uint64_t seed = argc > 4 ? strtoull(argv[4], nullptr, 0) : 1;
    return is_float ? run<float>(dense, elements, seed)
                    : run<double>(dense, elements, seed);
}
