#include <mpi.h>

#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <numeric>
#include <sstream>
#include <string>
#include <vector>

#ifdef ANNOTATE
extern "C" {
#include "annotate.h"
}
#endif // ANNOTATE

#ifdef USE_SVE
#include <arm_sve.h>
#endif

template <typename T>
void print_vector(const std::vector<T> &v)
{
    for (auto x : v)
        std::cout << x << ' ';
    std::cout << '\n';
}

template <typename T>
void read_array_from_file(const std::string &path, std::vector<T> &data)
{
    std::ifstream file(path);
    data.clear();

    std::string line;
    while (std::getline(file, line))
    {
        std::istringstream ss(line);
        T val;
        ss >> val;
        data.push_back(val);
    }
}

#ifdef USE_SVE
__attribute__((noinline)) double sum_indirect(const uint64_t *idx, const double *data, int n)
{
    svfloat64_t acc = svdup_f64(0.0);

    for (int i = 0; i < n; i += svcntd())
    {
        svbool_t pg = svwhilelt_b64(i, n);    // lanes still active
        svuint64_t vidx = svld1(pg, &idx[i]); // 64‑bit indices
        svfloat64_t v = svld1_gather_u64index_f64(pg, data, vidx);
        acc = svadd_f64_m(pg, acc, v); // predicated FMA
    }
    return svaddv_f64(svptrue_b64(), acc); // horizontal add
}
#else
__attribute__((noinline)) double sum_indirect(const uint64_t *idx, const double *data, int n)
{
    double sum = 0.0;
    for (int i = 0; i < n; ++i)
    {
        sum += data[idx[i]];
    }
    return sum;
}
#endif

/* ---------- main --------------------------------------------------------- */
int main(int argc, char **argv)
{
    MPI_Init(&argc, &argv);

    int world_rank = 0, world_size = 0;
    MPI_Comm_rank(MPI_COMM_WORLD, &world_rank);
    MPI_Comm_size(MPI_COMM_WORLD, &world_size);

    if (argc < 3)
    {
        if (world_rank == 0)
            std::cerr << "Usage: " << argv[0] << " <index_file> <data_file>\n";
        MPI_Abort(MPI_COMM_WORLD, 1);
    }

#ifdef ANNOTATE
    annotate_init_();
#endif // ANNOTATE

    int num_elements = 0;
    std::vector<uint64_t> index;
    std::vector<double> data;

    if (world_rank == 0)
    {
        read_array_from_file<uint64_t>(argv[1], index);
        read_array_from_file<double>(argv[2], data);
        std::cout << "Read " << index.size() << " indices and "
                  << data.size() << " data elements\n";

        // debug prints – comment out for production
        // print_vector(index);
        // print_vector(data);

        num_elements = static_cast<int>(index.size());
        if (num_elements != static_cast<int>(data.size()))
        {
            std::cerr << "Error: index and data sizes do not match\n";
            MPI_Abort(MPI_COMM_WORLD, 1);
        }
        auto [min_it, max_it] =
            std::minmax_element(index.begin(), index.end());
        if (*max_it >= static_cast<uint64_t>(data.size()))
        {
            std::cerr << "Error: index out of bounds of data array\n";
            MPI_Abort(MPI_COMM_WORLD, 1);
        }
    }

    MPI_Bcast(&num_elements, 1, MPI_INT, 0, MPI_COMM_WORLD);

    if (world_rank != 0)
        data.resize(num_elements);
    MPI_Bcast(data.data(), num_elements, MPI_DOUBLE, 0, MPI_COMM_WORLD);

    /* ---------- scatter indices ----------------------------------------- */
    int chunk = num_elements / world_size;
    int remainder = num_elements % world_size;
    int local_sz = chunk + (world_rank < remainder ? 1 : 0);

    std::vector<int> send_counts(world_size), displs(world_size);
    if (world_rank == 0)
    {
        for (int r = 0, off = 0; r < world_size; ++r)
        {
            send_counts[r] = chunk + (r < remainder ? 1 : 0);
            displs[r] = off;
            off += send_counts[r];
        }
    }

    std::vector<uint64_t> local_index(local_sz);
    MPI_Scatterv((world_rank == 0 ? index.data() : NULL),
                (world_rank == 0 ? send_counts.data() : NULL),
                (world_rank == 0 ? displs.data() : NULL),
                MPI_UINT64_T,
                local_index.data(), local_sz, MPI_UINT64_T, 0,
                MPI_COMM_WORLD);

    MPI_Barrier(MPI_COMM_WORLD);

#ifdef ANNOTATE
    roi_begin_();
#ifdef SYNC_ON_ROI
    annotate_synchronize_(1);
#endif // SYNC_ON_ROI
#endif // ANNOTATE
    double local_sum = sum_indirect(local_index.data(), data.data(), local_sz);
#ifdef ANNOTATE
    roi_end_();
#ifdef SYNC_ON_ROI
    annotate_synchronize_(2);
#endif // SYNC_ON_ROI
#endif // ANNOTATE
    double global_sum = 0.0;

    MPI_Reduce(&local_sum, &global_sum, 1, MPI_DOUBLE, MPI_SUM, 0, MPI_COMM_WORLD);

    if (world_rank == 0)
        std::cout << "Final sum: " << global_sum << '\n';

#ifdef ANNOTATE
    annotate_term_();
#endif // ANNOTATE

    MPI_Finalize();
    return 0;
}
