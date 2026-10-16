// Convert a Matrix Market coordinate file (e.g. from the SuiteSparse Matrix
// Collection) to the binary CSR file that `spmv csr <file>` reads, on the
// host, so that a simulation loads the matrix instead of parsing text.
//
// Usage: mtx2csr <in.mtx> <out.csr>
//
// Real, integer and pattern entries (pattern: every value 1.0); general,
// symmetric and skew-symmetric matrices (the other triangle is mirrored,
// negated for skew-symmetric). Columns are sorted within each row;
// duplicate entries are kept.
//
// Binary CSR layout (little-endian): the 8 bytes "SIFTCSR1"; int64 rows,
// cols, nnz; int64 row_ptr[rows + 1]; int32 col[nnz]; double val[nnz].

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <numeric>
#include <string>
#include <vector>

static void fail(const char *msg) {
    fprintf(stderr, "mtx2csr: %s\n", msg);
    exit(1);
}

int main(int argc, char **argv) {
    if (argc != 3)
        fail("usage: mtx2csr <in.mtx> <out.csr>");
    FILE *in = fopen(argv[1], "r");
    if (!in)
        fail("cannot open the input");

    std::vector<char> line(1 << 16);
    if (!fgets(line.data(), line.size(), in))
        fail("empty input");
    std::string banner(line.data());
    for (auto &c : banner)
        c = tolower(c);
    if (banner.find("matrixmarket") == std::string::npos ||
        banner.find("coordinate") == std::string::npos)
        fail("not a Matrix Market coordinate file");
    const bool pattern = banner.find("pattern") != std::string::npos;
    const bool skew = banner.find("skew-symmetric") != std::string::npos;
    const bool symmetric = skew || banner.find("symmetric") != std::string::npos ||
                           banner.find("hermitian") != std::string::npos;
    if (banner.find("complex") != std::string::npos)
        fail("complex matrices are not supported");

    while (fgets(line.data(), line.size(), in) && line[0] == '%') {
    }
    long long rows, cols, entries;
    if (sscanf(line.data(), "%lld %lld %lld", &rows, &cols, &entries) != 3)
        fail("bad size line");
    if (rows >= (1LL << 31) || cols >= (1LL << 31))
        fail("more than 2^31 rows or columns");

    std::vector<int32_t> r, c;
    std::vector<double> v;
    const size_t reserve = symmetric ? 2 * entries : entries;
    r.reserve(reserve);
    c.reserve(reserve);
    v.reserve(reserve);
    for (long long i = 0; i < entries; i++) {
        if (!fgets(line.data(), line.size(), in))
            fail("fewer entries than the size line says");
        char *p = line.data();
        long long ri = strtoll(p, &p, 10), ci = strtoll(p, &p, 10);
        double val = pattern ? 1.0 : strtod(p, &p);
        if (ri < 1 || ri > rows || ci < 1 || ci > cols)
            fail("entry out of range");
        r.push_back(int32_t(ri - 1));
        c.push_back(int32_t(ci - 1));
        v.push_back(val);
        if (symmetric && ri != ci) {
            r.push_back(int32_t(ci - 1));
            c.push_back(int32_t(ri - 1));
            v.push_back(skew ? -val : val);
        }
    }
    fclose(in);
    const int64_t nnz = int64_t(r.size());

    // Counting sort by row, then sort the columns of each row.
    std::vector<int64_t> row_ptr(rows + 1, 0);
    for (int64_t k = 0; k < nnz; k++)
        row_ptr[r[k] + 1]++;
    std::partial_sum(row_ptr.begin(), row_ptr.end(), row_ptr.begin());
    std::vector<int64_t> next(row_ptr.begin(), row_ptr.end() - 1);
    std::vector<int32_t> col(nnz);
    std::vector<double> val(nnz);
    for (int64_t k = 0; k < nnz; k++) {
        int64_t at = next[r[k]]++;
        col[at] = c[k];
        val[at] = v[k];
    }
    std::vector<int32_t>().swap(r);
    std::vector<int32_t>().swap(c);
    std::vector<double>().swap(v);
    std::vector<std::pair<int32_t, double>> row;
    for (long long i = 0; i < rows; i++) {
        row.clear();
        for (int64_t k = row_ptr[i]; k < row_ptr[i + 1]; k++)
            row.emplace_back(col[k], val[k]);
        std::sort(row.begin(), row.end(),
                  [](const auto &a, const auto &b) { return a.first < b.first; });
        for (size_t j = 0; j < row.size(); j++) {
            col[row_ptr[i] + j] = row[j].first;
            val[row_ptr[i] + j] = row[j].second;
        }
    }

    FILE *out = fopen(argv[2], "wb");
    if (!out)
        fail("cannot open the output");
    const int64_t header[3] = {rows, cols, nnz};
    if (fwrite("SIFTCSR1", 1, 8, out) != 8 ||
        fwrite(header, sizeof(int64_t), 3, out) != 3 ||
        fwrite(row_ptr.data(), sizeof(int64_t), rows + 1, out) != size_t(rows + 1) ||
        fwrite(col.data(), sizeof(int32_t), nnz, out) != size_t(nnz) ||
        fwrite(val.data(), sizeof(double), nnz, out) != size_t(nnz))
        fail("write failed");
    fclose(out);
    printf("%s: %lld rows, %lld columns, %lld nonzeros (%s%s)\n", argv[2], rows,
           cols, (long long)nnz, pattern ? "pattern" : "real",
           symmetric ? (skew ? ", skew-symmetric, expanded" : ", symmetric, expanded") : "");
    return 0;
}
