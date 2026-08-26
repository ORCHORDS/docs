# PyTorch compile recompilation budget

**Issue:** A model can be functionally correct under `torch.compile` yet repeatedly recompile as guards fail, spending more time compiling than executing and eventually reaching the compile cache limit.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Capture `TORCH_LOGS=recompiles` or a `tlparse` trace before changing compiler settings.
- Treat input shapes, Python values, module state, dtypes, devices, and global state as part of the compiled-call contract.
- Use `dynamic=True` only when the workload and backend support the required dynamic shapes; benchmark it against bounded shape buckets.
- Isolate genuinely dynamic or unsupported regions instead of raising cache limits blindly.
- Record compile time, graph count, guard-failure reason, steady-state latency, and eager fallback in performance evidence.

## Verification

Run cold and warm trials across every supported shape and state transition. Fail a regression test when graph or recompilation counts exceed the measured budget, and compare results with eager execution.

## Gotchas

Recompilation can be required for soundness. A graph break can reduce recompilation scope but also removes optimization opportunities. Raising the cache limit can hide unstable inputs while increasing memory and startup cost.

## Official sources

- [PyTorch: Dealing with recompilations](https://docs.pytorch.org/docs/main/user_guide/torch_compiler/compile/programming_model.recompilation.html)
- [PyTorch: Working with graph breaks](https://docs.pytorch.org/docs/main/user_guide/torch_compiler/compile/programming_model.graph_breaks_index.html)
