# Torch Export Dynamic-Shape Constraint Contract

**Issue:** A torch.export artifact traced from example inputs can be mistaken for a model that accepts every shape, even though its ExportedProgram records guards and relations that reject or mis-handle unqualified inputs.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Define dynamic dimensions deliberately with named Dim specifications, bounds, and relationships; do not infer a public input contract from one example.
- Preserve the exported program, constraint description, model digest, PyTorch version, decomposition choices, and example-input schema together.
- Treat suggested constraint fixes as reviewable API changes rather than applying them blindly.
- Validate shape, dtype, device, rank, and cross-input relations before invoking the exported program.
- Keep eager execution as the semantic oracle for the supported domain and fail closed outside that domain.
- Re-export and requalify after model control flow, preprocessing, or PyTorch changes.

## Implementation and tests

1. Export with minimum, typical, and maximum supported shapes represented in the design.
2. Execute every bound plus values just inside and just outside each bound.
3. Test equalities and affine relationships between dimensions across inputs.
4. Compare eager and exported results, mutations, and error behavior for all supported cases.
5. Confirm unsupported shapes fail before any external side effect.
6. Test serialization and loading in the actual deployment runtime.

## Gotchas and applicability

Export captures a constrained tensor program, not arbitrary Python behavior. Static-by-default dimensions and data-dependent control flow can narrow the artifact unexpectedly. Automatic and dynamic dimension modes differ across versions, so pin the documented PyTorch release. Successful export is not proof that a downstream backend supports the same constraints.

## Official sources

- https://docs.pytorch.org/docs/stable/export.html
- https://docs.pytorch.org/docs/stable/user_guide/torch_compiler/export.html
