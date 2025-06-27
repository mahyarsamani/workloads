#include <iostream>
#include <vector>
#include <numeric>
#include <chrono>

extern "C" {
#include "annotate.h"
#include "gups_kernels.h"
}


typedef uint64_t TElement;
typedef uint64_t TIndex;

size_t get_num_omp_threads();
void report(const size_t& numThreads, const size_t& numTableElements, const size_t& numUpdates, const double& elapsedTime);

int main(int argc, char* argv[])
{
    if (argc != 3)
    {
        std::cout << "Usage: " << argv[0] << " <number_of_elements_in_table> <number_of_updates_per_burst>" << std::endl;
        return 1;
    }
    annotate_init_();

    TIndex numTableElements = atoi(argv[1]);
    TIndex numUpdatesPerBurst = atoi(argv[2]);
    std::vector<TElement> table = std::vector<TElement>(numTableElements);
    std::iota(std::begin(table), std::end(table), 0); // filling the table with numbers from 0 to n-1

    TIndex numUpdates = numTableElements*4;

    const auto t_start = std::chrono::steady_clock::now();
    roi_begin_();

    doRandomAccess(table.data(), numTableElements, numUpdates, numUpdatesPerBurst);

    roi_end_();
    const auto t_end = std::chrono::steady_clock::now();
    std::chrono::duration<double> delta_t = t_end - t_start;

    size_t numThreads = get_num_omp_threads();

    report(numThreads, numTableElements, numUpdates, delta_t.count());

    annotate_term_();
    return 0;
}

size_t get_num_omp_threads()
{
    size_t num_threads = 0;
#ifdef _OPENMP
#pragma omp parallel
#pragma omp atomic
    num_threads++;
#endif
    return num_threads;
}

void report(const size_t& numThreads, const size_t& numTableElements, const size_t& numUpdates, const double& elapsedTime)
{
    std::cout << "Number of threads: " << numThreads <<std::endl;

    const double tableSizeGiB = 1.0 * numTableElements * sizeof(TElement) / 1024.0 / 1024.0 / 1024.0;
    std::cout << "Table Size: " << tableSizeGiB << " GiB" << std::endl;

    std::cout << "Number of Updates: " << numUpdates << std::endl;

    std::cout << "Time: " << elapsedTime << " seconds" << std::endl;

    const double effectiveBandwidth = 1.0 * numUpdates * sizeof(TElement) / 1024.0 / 1024.0 / 1024.0 / elapsedTime;
    std::cout << "Effective Bandwidth: " << effectiveBandwidth << " GiB/s" << std::endl;

    std::cout << "GUPS: " << numUpdates / elapsedTime / 1000000000.0 <<std::endl;
}
