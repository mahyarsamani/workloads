#include "hov.h"
#include <sys/mman.h>
#include <stdlib.h>
#include <stdio.h>

hov_pair_t hov_create_pair(void *data, void *index,
                           size_t data_elem_size,
                           size_t index_elem_size,
                           size_t count)
{
    hov_pair_t pair;
    pair.data_base = data;
    pair.index_base = index;
    pair.data_elem_size = data_elem_size;
    pair.index_elem_size = index_elem_size;
    pair.count = count;

    /* Allocate a VA region for aliases.
     * PROT_NONE: no actual access permitted — accidental dereference
     * segfaults immediately (fail-fast).
     * MAP_ANONYMOUS: no file backing; no physical pages committed. */
    size_t alias_region_size = count * data_elem_size;
    void *alias_region = mmap(NULL, alias_region_size,
                              PROT_NONE,
                              MAP_ANONYMOUS | MAP_PRIVATE,
                              -1, 0);
    if (alias_region == MAP_FAILED) {
        /* Fallback: PROT_READ (gem5 SE mode may not support PROT_NONE) */
        alias_region = mmap(NULL, alias_region_size,
                            PROT_READ,
                            MAP_ANONYMOUS | MAP_PRIVATE,
                            -1, 0);
        if (alias_region == MAP_FAILED) {
            perror("hov_create_pair: mmap failed");
            abort();
        }
    }
    pair.base_alias = alias_region;
    return pair;
}

void hov_destroy_pair(hov_pair_t *pair)
{
    if (pair->base_alias != NULL) {
        size_t alias_region_size = pair->count * pair->data_elem_size;
        munmap(pair->base_alias, alias_region_size);
        pair->base_alias = NULL;
    }
}
