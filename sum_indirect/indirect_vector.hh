// indirect_vector.hh
#ifndef INDIRECT_VECTOR_HH
#define INDIRECT_VECTOR_HH

#include <stdint.h>

#ifdef USE_SVE
#include <arm_sve.h>
#endif

#ifdef __cplusplus
extern "C" {
#endif

#ifdef USE_SVE

// -----------------------------------------------------------------------------
// VLDIND (Vector Load Indirect - Gather)
// Gathers values from `data_base` using indices from `index_base`.
// 
// Parameters:
//   val:        Pointer to a vector to store the loaded values.
//   val_addr:   Pointer to a vector to store the computed effective addresses.
//   stream_id:  The Stream ID (passed as a scalar or broadcast to vector lanes depending on implementation).
//   data_base:  Base pointer of the data array.
//   index_base: Base pointer of the index vector.
// -----------------------------------------------------------------------------

void vldind_f64v_u64i(svfloat64_t *val, svuint64_t *val_addr, uint64_t stream_id, const double *data_base, const svuint64_t *index_base);
void vldind_u64v_u64i(svuint64_t *val, svuint64_t *val_addr, uint64_t stream_id, const uint64_t *data_base, const svuint64_t *index_base);


// -----------------------------------------------------------------------------
// VSTIND (Vector Store Indirect - Scatter)
// Scatters elements from `val` to `data_base` using indices from `index_base`.
// 
// Parameters:
//   val_addr:   Pointer to an SVE vector to store the computed effective addresses.
//   stream_id:  The Stream ID.
//   data_base:  Base pointer of the data array.
//   index_base: Base pointer of the index vector.
//   val:        The SVE vector containing the values to store.
// -----------------------------------------------------------------------------

void vstind_f64v_u64i(svuint64_t *val_addr, uint64_t stream_id, double *data_base, const svuint64_t *index_base, svfloat64_t val);
void vstind_u64v_u64i(svuint64_t *val_addr, uint64_t stream_id, uint64_t *data_base, const svuint64_t *index_base, svuint64_t val);

#endif // USE_SVE

#ifdef __cplusplus
}
#endif

#endif // INDIRECT_VECTOR_HH
