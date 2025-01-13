#include <iostream>
#include <fstream>
#include <vector>
#include <algorithm>
#include <string>
#include <iterator>
#include <cassert>
#include <cstdint>
#include <cmath>
#include <cassert>
#include <chrono>

#include "json.hpp"

extern "C" {
#include "annotate.h"
#include "scatter_gather_kernels.h"
}


using json = nlohmann::json;

typedef double TElement;
typedef uint64_t TIndex;

size_t get_num_omp_threads();

enum KernelType { Gather = 0, Scatter };

class ScatterGatherKernel {
  private:
    std::vector<TIndex> index;
    KernelType kernel_type;
    TIndex multiplicity;
  public:
    ScatterGatherKernel() { kernel_type = KernelType::Gather; multiplicity = 0; }
    ScatterGatherKernel(std::vector<TIndex>& index, const KernelType& kernel_type, const TIndex& multiplicity) {
        this->setIndex(index);
        this->setType(kernel_type);
        this->setMultiplicity(multiplicity);
    }
    void setIndex(const std::vector<TIndex>& index) {
        this->index = std::move(index);
    }
    void setType(const KernelType& kernel_type) {
        this->kernel_type = kernel_type;
    }
    void setMultiplicity(const TIndex& multiplicity) {
        this->multiplicity = multiplicity;
    }
    size_t getMaxIndex() const {
        auto it = std::max_element(this->index.begin(), this->index.end());
        return std::max(*it, this->index.size());
    }
    size_t getNumIndex() const {
        return index.size();
    }
    void doPrint() const {
        std::cout << "Kernel" << std::endl;
        std::cout << "  + type: ";
        if (this->kernel_type == KernelType::Gather)
            std::cout << "Gather";
        else
            std::cout << "Scatter";
        std::cout << std::endl;
        std::cout << "  + size: " << this->index.size() << std::endl;
        std::cout << "  + index range: [0, " << this->getMaxIndex() << "]" << std::endl;
        std::cout << "  + multiplicity: " << this->multiplicity << std::endl;
    }
    void execute(std::vector<TElement>& dst, std::vector<TElement>& src) const {
        switch (this->kernel_type) {
            case KernelType::Gather:
                for (size_t iter = 0; iter < this->multiplicity; iter++)
                    gather(dst.data(), src.data(), this->index.data(), this->index.size());
                break;
            case KernelType::Scatter:
                for (size_t iter = 0; iter < this->multiplicity; iter++)
                    scatter(dst.data(), src.data(), this->index.data(), this->index.size());
                break;
            default:
                std::cout << "Warn: unregconized kernel type" << std::endl;
                break;
        }
    }
};

std::vector<ScatterGatherKernel> read_spatter_json(const char* filename) {
    std::vector<ScatterGatherKernel> kernels;
    std::ifstream idx_file(filename);
    json j = json::parse(idx_file);
    const size_t numKernels = j.size();
    kernels.reserve(numKernels);
    for (size_t i = 0; i < numKernels; i++) {
        kernels.push_back(ScatterGatherKernel());
        kernels.back().setIndex(j[i]["pattern"]);
        kernels.back().setMultiplicity(j[i]["count"]);
        if (j[i]["kernel"] == "Gather")
            kernels.back().setType(KernelType::Gather);
        else if (j[i]["kernel"] == "Scatter")
            kernels.back().setType(KernelType::Scatter);
    }
    idx_file.close();
    return kernels;
}

void executeKernels(const char* filename) {
    auto kernels = read_spatter_json(filename);
    const size_t num_kernels = kernels.size();

    std::vector<std::vector<TElement>> src;
    std::vector<std::vector<TElement>> dst;

    // create different src and dst arrays for different kernels
    for (auto const& k: kernels) {
        size_t array_size = pow(2, int(log2(k.getMaxIndex()+1))+1);
        src.emplace_back(std::move(std::vector<TElement>(array_size, 2)));
        dst.emplace_back(std::move(std::vector<TElement>(array_size, 3)));
    }

    double t_total = 0;
    std::vector<double> elapsed_time_per_kernel(num_kernels, 0.0);

    annotate_init_();
    roi_begin_();
    size_t kernelIdx = 0;
    for (auto const& k: kernels) {
        const auto t_start = std::chrono::steady_clock::now();
        k.execute(dst[kernelIdx], src[kernelIdx]);
        const auto t_end = std::chrono::steady_clock::now();
        std::chrono::duration<double> delta_t = t_end - t_start;
        elapsed_time_per_kernel[kernelIdx] = delta_t.count();
        kernelIdx += 1;
    }
    roi_end_();

    // Reporting
    double total_effective_data_size_in_bytes = 0;
    for (size_t t = 0; t < num_kernels; t++) {
        kernels[t].doPrint();
        std::cout << "Execute Time: " << elapsed_time_per_kernel[t] << " seconds" << std::endl;
        double effective_data_size_in_bytes = kernels[t].getNumIndex() * sizeof(TElement) * 2;
        double effective_data_size_in_GiB = effective_data_size_in_bytes / 1024.0 / 1024.0 / 1024.0;
        double effective_bandwidth = effective_data_size_in_GiB / elapsed_time_per_kernel[t];
        std::cout << "Effective Bandwidth: " << effective_bandwidth << " GiB/s" << std::endl;
        total_effective_data_size_in_bytes += effective_data_size_in_bytes; // 1 load and 1 store for 1 index
        t_total += elapsed_time_per_kernel[t];
    }
    std::cout << "Total Elapsed Time: " << (t_total) << " seconds" << std::endl;
    double total_effective_data_size_in_GiB = total_effective_data_size_in_bytes / 1024.0 / 1024.0 / 1024.0;
    double total_effective_bandwidth = total_effective_data_size_in_GiB / t_total;
    std::cout << "Total Effective Bandwidth: " << total_effective_bandwidth << " GiB/s" << std::endl;
}

int main(int argc, char* argv[]) {
    if (argc != 2) {
        std::cout << "Usage: " << argv[0] << " <path_to_json_file>" << std::endl;
        return 1;
    }
    const size_t num_threads = get_num_omp_threads();
    std::cout << "Number of threads: " << num_threads << std::endl;
    executeKernels(argv[1]);
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
