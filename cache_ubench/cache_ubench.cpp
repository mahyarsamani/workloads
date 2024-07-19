
#include <chrono>
#include <iostream>
#include <random>

#ifdef ANNOTATE
extern "C" {
#include "roi.h"
}
#endif //ANNOTATE

#ifndef ITERS_PER_TEST
#define ITERS_PER_TEST 16384
#endif // ITERS_PER_TEST

#ifndef L1_SIZE_BYTES
#define L1_SIZE_BYTES 65536
#endif // L1_SIZE_BYTES

#ifndef L2_SIZE_BYTES
#define L2_SIZE_BYTES 1048576
#endif // L2_SIZE_BYTES

#ifndef L3_SIZE_BYTES
#define L3_SIZE_BYTES 2097152
#endif // L3_SIZE_BYTES

void test_int(uint64_t cache_size, std::string name)
{
    uint64_t num_elements = cache_size / sizeof(double);
    uint64_t* array = new uint64_t[num_elements];

    std::random_device rd;
    std::mt19937 gen(rd());
    // TODO: Update to generate float64_t values
    std::uniform_int_distribution<uint64_t> dis(0, 128);

    std::cout << "Initializing an array with "
    << num_elements << " uint64_t elements." << std::endl;
    for (int i = 0; i < num_elements; i++) {
        array[i] = dis(gen);
    }
    std::cout << "Done initializing." << std::endl;


    uint64_t sum = 0;
#ifdef ANNOTATE
    annotate_init_();
#endif // ANNOTATE
    auto start = std::chrono::high_resolution_clock::now();
#ifdef ANNOTATE
    roi_begin_();
#endif // ANNOTATE
    for (uint64_t iteration = 0; iteration < ITERS_PER_TEST; iteration++) {
#ifdef PARALLEL
#ifdef SIMD
        #pragma omp parallel for simd
#else // SIMD
        #pragma omp parallel for
#endif // SIMD
#endif // PARALLEL
        for (int i = 0; i < num_elements; i+= 8) {
            sum += array[i + 0];
            sum += array[i + 1];
            sum += array[i + 2];
            sum += array[i + 3];
            sum += array[i + 4];
            sum += array[i + 5];
            sum += array[i + 6];
            sum += array[i + 7];
        }
    }
#ifdef ANNOTATE
    roi_end_();
#endif // ANNOTATE
    auto end = std::chrono::high_resolution_clock::now();

    auto duration = std::chrono::duration_cast<std::chrono::nanoseconds>(end - start);

    uint64_t num_accesses = num_elements * ITERS_PER_TEST;
    uint64_t bytes_accessed = cache_size * ITERS_PER_TEST;
    double avg_latency = ((double) duration.count() / num_accesses);
    double bandwidth_gbps = ((double) bytes_accessed / duration.count());
    std::cout << "Test Results for " << name << " Cache:" << std::endl;
    std::cout << "sum: " << sum << std::endl;
    std::cout << "duration: " << duration.count() << " ns" << std::endl;
    std::cout << "number of accesses: " << num_accesses << std::endl;
    std::cout << "bytes accessed: " << bytes_accessed << std::endl;
    std::cout << "average latency: " << avg_latency << " ns" << std::endl;
    std::cout << "bandwidth: " << bandwidth_gbps << " GB/s" << std::endl;

    delete [] array;
    return;
}

void test_fp(uint64_t cache_size, std::string name)
{
    uint64_t num_elements = cache_size / sizeof(double);
    double* array = new double[num_elements];

    std::random_device rd;
    std::mt19937 gen(rd());
    // TODO: Update to generate float64_t values
    std::uniform_real_distribution<double> dis(0.0, 128.0);

    std::cout << "Initializing an array with "
    << num_elements << " double elements." << std::endl;
    for (int i = 0; i < num_elements; i++) {
        array[i] = dis(gen);
    }
    std::cout << "Done initializing." << std::endl;


    double sum = 0;
#ifdef ANNOTATE
    annotate_init_();
#endif // ANNOTATE
    auto start = std::chrono::high_resolution_clock::now();
#ifdef ANNOTATE
    roi_begin_();
#endif // ANNOTATE
    for (uint64_t iteration = 0; iteration < ITERS_PER_TEST; iteration++) {
#ifdef PARALLEL
#ifdef SIMD
        #pragma omp parallel for simd
#else // SIMD
        #pragma omp parallel for
#endif // SIMD
#endif // PARALLEL
        for (int i = 0; i < num_elements; i+= 8) {
            sum += array[i + 0];
            sum += array[i + 1];
            sum += array[i + 2];
            sum += array[i + 3];
            sum += array[i + 4];
            sum += array[i + 5];
            sum += array[i + 6];
            sum += array[i + 7];
        }
    }
#ifdef ANNOTATE
    roi_end_();
#endif // ANNOTATE
    auto end = std::chrono::high_resolution_clock::now();

    auto duration = std::chrono::duration_cast<std::chrono::nanoseconds>(end - start);

    uint64_t num_accesses = num_elements * ITERS_PER_TEST;
    uint64_t bytes_accessed = cache_size * ITERS_PER_TEST;
    double avg_latency = ((double) duration.count() / num_accesses);
    double bandwidth_gbps = ((double) bytes_accessed / duration.count());
    std::cout << "Test Results for " << name << " Cache:" << std::endl;
    std::cout << "sum: " << sum << std::endl;
    std::cout << "duration: " << duration.count() << " ns" << std::endl;
    std::cout << "number of accesses: " << num_accesses << std::endl;
    std::cout << "bytes accessed: " << bytes_accessed << std::endl;
    std::cout << "average latency: " << avg_latency << " ns" << std::endl;
    std::cout << "bandwidth: " << bandwidth_gbps << " GB/s" << std::endl;

    delete [] array;
    return;
}

int main(int argc, char** argv)
{
    if (argc != 2) {
        std::cout << "To run the cache bandwidth test please use this binary "
        << "like below:" << "\n\tcache_bandwidth {l1, l2, l3}" << std::endl;
        return 1;
    }

    std::string target = argv[1];

#if defined(INT)
    if (target == "l1") {
        test_int(L1_SIZE_BYTES, "L1");
    } else if (target == "l2") {
        test_int(L2_SIZE_BYTES, "L2");
    } else if (target == "l3") {
        test_int(L3_SIZE_BYTES, "L3");
    } else {
        std::cerr << "Target: " << target << " not recognized." << std::endl;
        return -1;
    }
#elif defined(FP)
    if (target == "l1") {
        test_fp(L1_SIZE_BYTES, "L1");
    } else if (target == "l2") {
        test_fp(L2_SIZE_BYTES, "L2");
    } else if (target == "l3") {
        test_fp(L3_SIZE_BYTES, "L3");
    } else {
        std::cerr << "Target: " << target << " not recognized." << std::endl;
        return -1;
    }
#else
    #error "Define INT or FP to run the test."
#endif // INT or FP

    return 0;
}