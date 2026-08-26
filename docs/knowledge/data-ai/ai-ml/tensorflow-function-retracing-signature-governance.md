# Govern TensorFlow Function Retracing with Signatures

**Issue:** `tf.function` creates specialized ConcreteFunctions for argument TraceTypes. Python values, changing shapes, and new objects can cause repeated tracing, latency spikes, and graph growth.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Define `input_signature` for stable tensor interfaces where practical.
- Pass tensors rather than frequently changing Python scalars into traced control flow.
- Bound intended polymorphism and record ConcreteFunction count.
- Keep Python side effects out of assumptions about per-call graph execution.
- Review custom TraceType implementations for equality, placeholder, and casting semantics.

## Verification
- Sweep batch shapes, dtypes, Python values, containers, and custom objects while counting traces.
- Test first-call and steady-state latency independently.
- Assert unsupported shapes fail at the interface rather than creating uncontrolled variants.

## Gotchas
Tracing executes Python to build a graph; graph execution does not replay arbitrary Python side effects. Relaxed shapes can reduce traces while weakening shape-specific optimization.

## Official sources
- [TensorFlow tf.function](https://www.tensorflow.org/api_docs/python/tf/function)
- [TensorFlow Function guide](https://www.tensorflow.org/guide/function)
