# JAX transfer guard device boundary

**Issue:** An implicit host/device transfer can silently synchronize accelerators, inflate latency, and move sensitive tensors across an intended execution boundary. JAX transfer guards can expose or reject those transfers, but their direction and scope must be configured deliberately.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Set separate policy for host-to-device, device-to-device, and device-to-host transfers when their risks differ.
- Begin with logging in representative workloads, classify each reported transfer, then move validated paths to a disallow policy.
- Make intended transfers explicit with documented JAX APIs instead of weakening the guard around a whole request.
- Apply global configuration during process startup, before worker threads are created. Use thread-local context only for the smallest reviewed operation.
- Treat transfer-guard logs as performance and data-boundary telemetry; redact tensor-derived values and correlate events with request and model identifiers safely.

## Implementation and tests

JAX supports `allow`, `log`, `disallow`, `log_explicit`, and `disallow_explicit` levels. Configure all transfers together or use the direction-specific settings. Exercise an explicit device placement, an accidental host-to-device conversion, cross-device movement, and host materialization. Assert the expected warning or exception for every direction.

Run tests in newly created worker threads as well as the main thread. Verify both success and failure paths do not leave a permissive thread-local context active. Benchmark with guards enabled so diagnostic policy is not removed from the measured runtime.

## Gotchas and applicability

“Explicit” describes how JAX observes the transfer, not whether the business operation is authorized. Some library internals may perform necessary transfers, so a disallow rollout needs workload coverage. New threads inherit the global setting, not another thread’s local context. JAX documents CPU device-to-host movement as always allowed because host and CPU device memory are not separated in the same way; do not use the guard as a universal data-loss-prevention control.

Transfer guards are a development and runtime diagnostic control, not proof of device isolation or confidentiality.

## Official sources

- [JAX: Transfer guard](https://docs.jax.dev/en/latest/transfer_guard.html)
- [JAX configuration options](https://docs.jax.dev/en/latest/config_options.html)
