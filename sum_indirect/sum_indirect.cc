#include "sum_indirect.hh"

#include <cstdint>
#include <iostream>
#include <string>
#include <vector>

#ifdef ANNOTATE
extern "C" {
#include "annotate.h"
}
#endif // ANNOTATE

/* ---------- main --------------------------------------------------------- */
int main(int argc, char **argv)
{
    if (argc < 3)
    {
        std::cerr << "Usage: " << argv[0] << " <index_file> <data_file>" << std::endl;
    }

#ifdef ANNOTATE
    annotate_init_();
#endif // ANNOTATE

    int num_elements = 0;
    std::vector<uint64_t> index;
    std::vector<double> data;

    read_array_from_file<uint64_t>(argv[1], index);
    read_array_from_file<double>(argv[2], data);
    if (static_cast<int>(index.size()) != static_cast<int>(data.size())) {
        std::cerr << "Index and data arrays should be of the same size." << std::endl;
    }
    num_elements = static_cast<int>(index.size());
    std::cout << "Read " << num_elements << " elements." << std::endl;

#ifdef DEBUG
    std::cout << "arr index:" << std::endl;
    print_vector(index);
    std::cout << "arr data:" << std::endl;
    print_vector(data);
#endif // DEBUG

#ifdef ANNOTATE
    roi_begin_();
#endif // ANNOTATE
    double sum = sum_indirect(index.data(), data.data(), num_elements);
#ifdef ANNOTATE
    roi_end_();
#endif // ANNOTATE
    std::cout << "Total sum: " << sum << std::endl;
#ifdef ANNOTATE
    annotate_term_();
#endif // ANNOTATE

    return 0;
}
