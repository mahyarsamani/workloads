#include<stdint.h>
#include<vector>
#include<cassert>
#include<chrono>
#include<iostream>

extern "C" {
#include "annotate.h"
#include "scatter_kernel.h"
}

typedef uint64_t TElement;
typedef uint64_t TIndex;

size_t get_num_omp_threads();

class IndexGenerator
{
    private:
        TIndex seed;
        TIndex mod;
        TIndex next_index;
    public:
        IndexGenerator()
        {
        }
        IndexGenerator(TIndex seed, TIndex mod)
        {
            // To have a sparse distribution of the indices, `mod` should be a prime number
            this->seed = seed;
            this->mod = mod;
            this->next_index = seed;
        }
        void reset()
        {
            this->next_index = this->seed;
        }
        TIndex next()
        {
            TIndex curr_index = this->next_index;
            this->next_index *= seed;
            this->next_index %= mod;
            return curr_index;
        }
};

int main(int argc, char* argv[])
{
    if (!((argc == 1) || (argc == 3)))
    {
        std::cout << "Usage:    " << argv[0] << std::endl;
        std::cout << "       or " << argv[0] << " <seed> <mod>" << std::endl;
        std::cout << "where multiplicative_order(seed, mod) = mod-1." <<std::endl;
        std::cout << "If seed and mod are not supplied, the default seed is 17 and the default mod is 100000007." << std::endl;
        return 1;
    }
    const int SEED = (argc == 1) ? 17 : atoi(argv[1]);
    const int MOD = (argc == 1) ? 100'000'007 : atoi(argv[2]);
    const int SIZE = MOD - 1;
    const int N_INDEX = SIZE;

    const size_t num_threads = get_num_omp_threads();
    std::cout << "Number of threads: " << num_threads << std::endl;

    std::vector<TElement> src(SIZE, 0);
    std::vector<TElement> dst(SIZE, 0);
    std::vector<TIndex> indices(N_INDEX, 0);

    // Initialize the arrays
    for (TIndex i = 0; i < SIZE; i++)
        src[i] = i;

    // Creating index
    const TElement seed = SEED;
    const TElement mod = MOD;
    // This index generator will essentially perform a permutation of the src to the dst
    IndexGenerator rng(seed, mod);
    for (TIndex i = 0; i < N_INDEX; i++)
        indices[i] = rng.next()-1;



    const auto t_start = std::chrono::steady_clock::now();
    annotate_init_();
    roi_begin_();

    // Performing indexed-stores
    scatter(dst.data(), src.data(), indices.data(), indices.size());

    roi_end_();
    const auto t_end = std::chrono::steady_clock::now();
    std::chrono::duration<double> elapsed_time = std::chrono::duration_cast<std::chrono::duration<double>>(t_end - t_start);

    // https://stackoverflow.com/questions/57538507/how-to-convert-stdchronoduration-to-double-seconds
    using namespace std::literals::chrono_literals;
    double time = elapsed_time / 1.0s; // converting from duration to double
    double data_size = 1.0 * SIZE * sizeof(TElement) * 2;
    double bandwidth_bytes = data_size / time;
    double bandwidth_GiB = bandwidth_bytes / 1024.0 / 1024.0 / 1024.0;

    std::cout << "Elapsed time: " << time << " s" << std::endl;
    std::cout << "Effective bandwidth: " << bandwidth_GiB << " GiB/s" << std::endl;

    // Checking result
    rng.reset();
    for (TIndex i = 0; i < N_INDEX; i++)
        assert(dst[rng.next()-1] == i);

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

