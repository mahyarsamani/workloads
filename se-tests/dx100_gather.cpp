// DX100 Sprint 1 test (projects/sift/docs/plans/dx100-port-plan.md, Sec. 6):
// one gather of a 4096-element array into a tile, read back uncached.
//
// The core streams an index array into one tile (maa_stream_load: one
// stream-read instruction) and gathers data[idx[i]] into another
// (maa_indirect_load: one indirect-read instruction), waits for the second
// tile, then reads it word by word through the accelerator's register port
// (the non-cacheable scratchpad range) and checks every element against the
// CPU's own data[idx[i]]. Prints "dx100_gather: match" and returns 0 on
// success, prints the mismatches and returns 1 otherwise.
//
// Single-threaded, no ROI markers: the SE wrapper runs it on O3 cores from
// the start. Built by scripts/build-se-kernels.sh, flavour gem5se-dx100.
#include <cstdint>
#include <cstdio>
#include <cstdlib>

#include "MAA_gem5.hpp"

static const int N = 4096;           // gathered elements (one tile holds 16K)
static const int M = 1 << 18;        // data elements (1 MiB of uint32_t)

int main() {
    uint32_t *idx = (uint32_t *)aligned_alloc(64, N * sizeof(uint32_t));
    uint32_t *data = (uint32_t *)aligned_alloc(64, M * sizeof(uint32_t));
    if (idx == nullptr || data == nullptr) {
        printf("dx100_gather: allocation failed\n");
        return 2;
    }
    // A fixed pseudo-random index stream (xorshift32) over the whole array,
    // and data that names its own position.
    uint32_t state = 0x2545F491u;
    for (int i = 0; i < N; i++) {
        state ^= state << 13;
        state ^= state >> 17;
        state ^= state << 5;
        idx[i] = state % M;
    }
    for (int j = 0; j < M; j++) {
        data[j] = 3u * (uint32_t)j + 7u;
    }

    alloc_MAA();
    init_MAA();
    add_mem_region(idx, idx + N);
    add_mem_region(data, data + M);

    int min_reg = get_new_reg<int>(0);
    int max_reg = get_new_reg<int>(N);
    int stride_reg = get_new_reg<int>(1);
    int idx_tile = get_new_tile<uint32_t>();
    int dst_tile = get_new_tile<uint32_t>();

    maa_stream_load<uint32_t>(idx, min_reg, max_reg, stride_reg, idx_tile);
    maa_indirect_load<uint32_t>(data, idx_tile, dst_tile);
    wait_ready(dst_tile);

    uint16_t size = get_tile_size(dst_tile);
    volatile uint32_t *tile = get_noncacheable_tile_pointer<uint32_t>(dst_tile);
    int mismatches = 0;
    for (int i = 0; i < N; i++) {
        uint32_t got = tile[i];
        uint32_t want = data[idx[i]];
        if (got != want) {
            if (mismatches < 16) {
                printf("dx100_gather: [%d] idx %u: got %u, want %u\n", i,
                       idx[i], got, want);
            }
            mismatches++;
        }
    }
    if (size != N) {
        printf("dx100_gather: tile size %u, want %d\n", size, N);
        mismatches++;
    }
    if (mismatches != 0) {
        printf("dx100_gather: %d mismatches\n", mismatches);
        return 1;
    }
    printf("dx100_gather: match (%d elements)\n", N);
    return 0;
}
