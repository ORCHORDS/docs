# TensorFlow Operation Determinism Is a Performance Contract

**Issue:** Reproducible seeds alone do not guarantee identical TensorFlow results; nondeterministic kernels, input pipelines, hardware, and software versions can still vary.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Enable operation determinism before building the training/input pipeline where reproducibility is required.
- Set all relevant random seeds and record hardware, drivers, TensorFlow, libraries, data order, and distribution strategy.
- Fail explicitly when an operation lacks a deterministic implementation.
- Qualify throughput and memory after enabling determinism because deterministic paths can be slower.
- Keep statistical reproducibility requirements separate from bitwise identity.

## Verification
- Repeat identical steps in fresh processes and compare outputs, gradients, and checkpoints.
- Exercise parallel input mapping, GPU kernels, distributed workers, and restart.
- Detect accidental version/hardware drift in the run manifest.

## Gotchas
Determinism is not promised across TensorFlow versions or different hardware configurations. Enabling it can serialize or replace fast kernels.

## Official sources
- [TensorFlow operation determinism](https://www.tensorflow.org/api_docs/python/tf/config/experimental/enable_op_determinism)
