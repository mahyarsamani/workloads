// #include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
// #include <numeric>
#include <sstream>
#include <string>
#include <vector>

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

#include "indirect_scalar.hh"

inline __attribute__((always_inline)) double sum_indirect_scalar_custom(const uint64_t *idx, const double *data, int n, uint64_t stream_id)
{
    double sum = 0.0;
    double val;
    uint64_t val_addr;
    
    for (int i = 0; i < n; ++i)
    {
        // Load the value using the custom indirect instruction interface
        ldind_f64v_u64i(&val, &val_addr, stream_id, data, idx, i);
        sum += val;
    }
    return sum;
}

#ifdef USE_SVE

#include "indirect_vector.hh"

inline __attribute__((always_inline)) double sum_indirect_vector_custom(const uint64_t *idx, const double *data, int n, uint64_t stream_id)
{
    svfloat64_t acc = svdup_f64(0.0);
    svfloat64_t val;
    svuint64_t val_addr;

    for (int i = 0; i < n; i += svcntd())
    {
        svbool_t pg = svwhilelt_b64(i, n);    // lanes still active
        
        // create a vector of indices
        svuint64_t vidx = svld1(pg, &idx[i]);

        // Load values using our custom SVE gather wrapper
        // The implementation must handle 'pg' predication internally or assume full vectors 
        // with the final fractional block padded with zeros or discarded.
        vldind_f64v_u64i(&val, &val_addr, stream_id, data, &vidx);
        
        acc = svadd_f64_m(pg, acc, val); 
    }
    return svaddv_f64(svptrue_b64(), acc); // horizontal add
}

#endif
