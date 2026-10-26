# UME-kernels

Standalone OpenMP versions of four UME gradient kernels (gradzatp, gradzatz, and their `_invert` forms), taken from the DX100 artifact.

## Origin
- Copied unmodified from `benchmarks/UME/` of https://github.com/arkhadem/DX100 at commit `e4fc4afdf894f295442cef3604667a469fab8e62` (2026-10-13), MIT license (`LICENSE`).
- Reference: A. Khadem et al., "DX100: A Programmable Data Access Accelerator for Indirection", ISCA 2025.
- Left out: the prebuilt x86 `m5op.o`, and DX100's accelerator API headers (`benchmarks/API/`), which only the `_maa` binaries need.

## What the kernels are
The kernels do not read a UME mesh.
`main` builds random index maps: `c_to_z[c]` and `c_to_p[c]` are `c` plus a uniform random offset in [-85000, 85000] (`DISTANCE_OTEHRS`), with 90000 entries of padding on each side, on `float` data.
The window follows the paper's measured average index distance on its UME input; the structure of a real mesh (a zone's corners are consecutive) is not kept.
The scatter-adds use `omp atomic`.

## Changes for SIFT
Changes made here after the copy are listed in this repository's history.
