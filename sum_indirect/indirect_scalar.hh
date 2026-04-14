// indirect_scalar.hh
#ifndef INDIRECT_SCALAR_HH
#define INDIRECT_SCALAR_HH

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// -----------------------------------------------------------------------------
// LDIND (Load Indirect)
// Loads value from (data_base + index_base[index] * sizeof(val))
// 
// Parameters:
//   val:        Pointer to store the loaded value.
//   val_addr:   Pointer to store the computed effective address accessed.
//   stream_id:  The ID of the stream this memory request belongs to.
//   data_base:  Base pointer of the data array.
//   index_base: Base pointer of the index array.
//   index:      The offset into the index array.
// -----------------------------------------------------------------------------

void ldind_f64v_u32i(double *val, uint64_t *val_addr, uint64_t stream_id, const double *data_base, const uint32_t *index_base, uint32_t index);
void ldind_f64v_u64i(double *val, uint64_t *val_addr, uint64_t stream_id, const double *data_base, const uint64_t *index_base, uint32_t index);

void ldind_u64v_u32i(uint64_t *val, uint64_t *val_addr, uint64_t stream_id, const uint64_t *data_base, const uint32_t *index_base, uint32_t index);
void ldind_u64v_u64i(uint64_t *val, uint64_t *val_addr, uint64_t stream_id, const uint64_t *data_base, const uint64_t *index_base, uint32_t index);


// -----------------------------------------------------------------------------
// STIND (Store Indirect)
// Stores value to (data_base + index_base[index] * sizeof(val))
// 
// Parameters:
//   val_addr:   Pointer to store the computed effective address accessed.
//   stream_id:  The ID of the stream this memory request belongs to.
//   data_base:  Base pointer of the data array.
//   index_base: Base pointer of the index array.
//   index:      The offset into the index array.
//   val:        The value to store.
// -----------------------------------------------------------------------------

void stind_f64v_u32i(uint64_t *val_addr, uint64_t stream_id, double *data_base, const uint32_t *index_base, uint32_t index, double val);
void stind_f64v_u64i(uint64_t *val_addr, uint64_t stream_id, double *data_base, const uint64_t *index_base, uint32_t index, double val);

void stind_u64v_u32i(uint64_t *val_addr, uint64_t stream_id, uint64_t *data_base, const uint32_t *index_base, uint32_t index, uint64_t val);
void stind_u64v_u64i(uint64_t *val_addr, uint64_t stream_id, uint64_t *data_base, const uint64_t *index_base, uint32_t index, uint64_t val);

#ifdef __cplusplus
}
#endif

#endif // INDIRECT_SCALAR_HH
