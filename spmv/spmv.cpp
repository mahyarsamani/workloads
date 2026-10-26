// CSR sparse matrix-vector product, y = A x, parallel over rows with
// OpenMP. Two products are marked (workloads/annotate: gem5 work
// begin/end in the gem5se flavour, no-ops in the native one), the warm-up
// and then the region of interest, and the result is checked against a
// serial product.
//
// The matrix sets how regular the gather x[col[k]] is:
//   spmv stencil27 <n>          27-point stencil on an n^3 grid (HPCG's)
//   spmv uniform <rows> <nnz>   <nnz> columns per row, uniformly random
//   spmv mtx <file>             a Matrix Market file (e.g. SuiteSparse)
//   spmv csr <file>             a binary CSR file from mtx2csr (the same
//                               matrices, loaded without parsing text)
// Option after the matrix: --seed <s> (uniform, default 1).

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <random>
#include <sstream>
#include <string>
#include <vector>

#include <omp.h>

#ifdef ANNOTATE
extern "C" {
#include "annotate.h"
}
#endif

#ifdef SIFT_HOV
// SIFT (built with -DSIFT_HOV): the region of interest gathers x[col[k]]
// with ldind, through the pair (x, col) bound to this side-car entry on
// every thread; the warm-up product runs the ref loop.
#include "hov.h"
#define HOV_ENTRY_X 0
#endif

struct CSR {
    int64_t rows = 0, cols = 0;
    std::vector<int64_t> row_ptr;
    std::vector<int32_t> col;
    std::vector<double> val;
};

static CSR stencil27(int64_t n) {
    CSR a;
    a.rows = a.cols = n * n * n;
    a.row_ptr.reserve(a.rows + 1);
    a.row_ptr.push_back(0);
    for (int64_t z = 0; z < n; z++)
        for (int64_t y = 0; y < n; y++)
            for (int64_t x = 0; x < n; x++) {
                for (int64_t dz = -1; dz <= 1; dz++)
                    for (int64_t dy = -1; dy <= 1; dy++)
                        for (int64_t dx = -1; dx <= 1; dx++) {
                            int64_t xx = x + dx, yy = y + dy, zz = z + dz;
                            if (xx < 0 || yy < 0 || zz < 0 || xx >= n || yy >= n || zz >= n)
                                continue;
                            bool diag = dx == 0 && dy == 0 && dz == 0;
                            a.col.push_back((int32_t)(xx + n * (yy + n * zz)));
                            a.val.push_back(diag ? 26.0 : -1.0);
                        }
                a.row_ptr.push_back((int64_t)a.col.size());
            }
    return a;
}

static CSR uniform(int64_t rows, int64_t nnz, uint64_t seed) {
    CSR a;
    a.rows = a.cols = rows;
    std::mt19937_64 rng(seed);
    std::uniform_int_distribution<int32_t> pick(0, (int32_t)(rows - 1));
    std::uniform_real_distribution<double> value(-1.0, 1.0);
    a.row_ptr.reserve(rows + 1);
    a.row_ptr.push_back(0);
    std::vector<int32_t> row_cols;
    for (int64_t r = 0; r < rows; r++) {
        row_cols.clear();
        for (int64_t k = 0; k < nnz; k++)
            row_cols.push_back(pick(rng));
        std::sort(row_cols.begin(), row_cols.end());
        for (int32_t c : row_cols) {
            a.col.push_back(c);
            a.val.push_back(value(rng));
        }
        a.row_ptr.push_back((int64_t)a.col.size());
    }
    return a;
}

// Matrix Market coordinate format: real, integer or pattern entries,
// general or symmetric (the other triangle is mirrored).
static CSR mtx(const std::string &path) {
    std::ifstream in(path);
    if (!in) {
        fprintf(stderr, "Cannot open %s\n", path.c_str());
        exit(2);
    }
    std::string line;
    std::getline(in, line);
    bool pattern = line.find("pattern") != std::string::npos;
    bool symmetric = line.find("symmetric") != std::string::npos;
    while (std::getline(in, line) && !line.empty() && line[0] == '%') {
    }
    int64_t rows, cols, entries;
    std::istringstream(line) >> rows >> cols >> entries;
    std::vector<std::pair<int32_t, std::pair<int32_t, double>>> coo;
    coo.reserve(symmetric ? 2 * entries : entries);
    for (int64_t i = 0; i < entries; i++) {
        int64_t r, c;
        double v = 1.0;
        in >> r >> c;
        if (!pattern)
            in >> v;
        coo.push_back({(int32_t)(r - 1), {(int32_t)(c - 1), v}});
        if (symmetric && r != c)
            coo.push_back({(int32_t)(c - 1), {(int32_t)(r - 1), v}});
    }
    std::sort(coo.begin(), coo.end());
    CSR a;
    a.rows = rows;
    a.cols = cols;
    a.row_ptr.assign(rows + 1, 0);
    for (auto &e : coo) {
        a.row_ptr[e.first + 1]++;
        a.col.push_back(e.second.first);
        a.val.push_back(e.second.second);
    }
    for (int64_t r = 0; r < rows; r++)
        a.row_ptr[r + 1] += a.row_ptr[r];
    return a;
}

// The binary CSR file of mtx2csr (the 8 bytes "SIFTCSR1"; int64 rows,
// cols, nnz; int64 row_ptr[rows + 1]; int32 col[nnz]; double val[nnz]):
// a simulation reads it with a few large reads instead of parsing text.
static CSR csr(const std::string &path) {
    FILE *in = fopen(path.c_str(), "rb");
    if (!in) {
        fprintf(stderr, "Cannot open %s\n", path.c_str());
        exit(2);
    }
    char magic[8];
    int64_t header[3];
    if (fread(magic, 1, 8, in) != 8 || memcmp(magic, "SIFTCSR1", 8) != 0 ||
        fread(header, sizeof(int64_t), 3, in) != 3) {
        fprintf(stderr, "%s is not a SIFTCSR1 file\n", path.c_str());
        exit(2);
    }
    CSR a;
    a.rows = header[0];
    a.cols = header[1];
    a.row_ptr.resize(a.rows + 1);
    a.col.resize(header[2]);
    a.val.resize(header[2]);
    if (fread(a.row_ptr.data(), sizeof(int64_t), a.rows + 1, in) != size_t(a.rows + 1) ||
        fread(a.col.data(), sizeof(int32_t), header[2], in) != size_t(header[2]) ||
        fread(a.val.data(), sizeof(double), header[2], in) != size_t(header[2])) {
        fprintf(stderr, "%s is truncated\n", path.c_str());
        exit(2);
    }
    fclose(in);
    return a;
}

static void spmv(const CSR &a, const std::vector<double> &x, std::vector<double> &y) {
    const int64_t *row_ptr = a.row_ptr.data();
    const int32_t *col = a.col.data();
    const double *val = a.val.data();
    const double *xv = x.data();
    double *yv = y.data();
#pragma omp parallel for schedule(static)
    for (int64_t r = 0; r < a.rows; r++) {
        double sum = 0.0;
        for (int64_t k = row_ptr[r]; k < row_ptr[r + 1]; k++)
            sum += val[k] * xv[col[k]];
        yv[r] = sum;
    }
}

#ifdef SIFT_HOV
static void spmv_hov(const CSR &a, const hov_pair_t *x_pair,
                     std::vector<double> &y) {
    const int64_t *row_ptr = a.row_ptr.data();
    const double *val = a.val.data();
    double *yv = y.data();
#pragma omp parallel for schedule(static)
    for (int64_t r = 0; r < a.rows; r++) {
        double sum = 0.0;
        for (int64_t k = row_ptr[r]; k < row_ptr[r + 1]; k++) {
            hov_result_f64_u32_t x;
            hov_gather_f64_u32(&x, HOV_ENTRY_X, x_pair, k);
            sum += val[k] * x.data_val;
        }
        yv[r] = sum;
    }
}
#endif

static void usage(const char *name) {
    fprintf(stderr,
            "Usage: %s stencil27 <n> | uniform <rows> <nnz> | mtx <file> | csr <file>"
            " [--seed <s>]\n",
            name);
    exit(2);
}

int main(int argc, char **argv) {
    if (argc < 3)
        usage(argv[0]);
    std::string kind = argv[1];
    int next = 3;
    uint64_t seed = 1;
    if (kind == "uniform") {
        if (argc < 4)
            usage(argv[0]);
        next = 4;
    }
    for (int i = next; i < argc; i++) {
        std::string opt = argv[i];
        if (opt == "--seed" && i + 1 < argc)
            seed = std::stoull(argv[++i]);
        else
            usage(argv[0]);
    }

    CSR a;
    if (kind == "stencil27")
        a = stencil27(std::stoll(argv[2]));
    else if (kind == "uniform")
        a = uniform(std::stoll(argv[2]), std::stoll(argv[3]), seed);
    else if (kind == "mtx")
        a = mtx(argv[2]);
    else if (kind == "csr")
        a = csr(argv[2]);
    else
        usage(argv[0]);
    printf("Matrix %s: %ld rows, %ld columns, %zu nonzeros, %d threads\n",
           kind.c_str(), (long)a.rows, (long)a.cols, a.col.size(), omp_get_max_threads());

    std::vector<double> x(a.cols), y(a.rows, 0.0);
    for (int64_t c = 0; c < a.cols; c++)
        x[c] = 1.0 + (double)(c % 7) / 7.0;
#ifdef SIFT_HOV
    hov_pair_t x_pair = hov_create_pair(x.data(), a.col.data(), sizeof(double),
                                        sizeof(int32_t), a.col.size());
#pragma omp parallel
    hov_bind_pair(HOV_ENTRY_X, &x_pair);
#endif

    // The warm-up product.
#ifdef ANNOTATE
    roi_begin_();
#endif
    spmv(a, x, y);
#ifdef ANNOTATE
    roi_end_();
#endif

    // The region of interest.
#ifdef ANNOTATE
    roi_begin_();
#endif
    double start = omp_get_wtime();
#ifdef SIFT_HOV
    spmv_hov(a, &x_pair, y);
#else
    spmv(a, x, y);
#endif
    double seconds = omp_get_wtime() - start;
#ifdef ANNOTATE
    roi_end_();
#endif
    printf("Product time: %.6f s\n", seconds);

    for (int64_t r = 0; r < a.rows; r++) {
        double ref = 0.0;
        for (int64_t k = a.row_ptr[r]; k < a.row_ptr[r + 1]; k++)
            ref += a.val[k] * x[a.col[k]];
        if (std::fabs(ref - y[r]) > 1e-9 * std::max(1.0, std::fabs(ref))) {
            printf("Mismatch at row %ld: %.17g (ref %.17g)\n", (long)r, y[r], ref);
            printf("Verification: FAIL\n");
            return 1;
        }
    }
    printf("Verification: PASS\n");
    return 0;
}
