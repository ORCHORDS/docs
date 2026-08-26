# Audit ONNX Runtime Execution-Provider Fallback

**Issue:** A model can silently run nodes—or an entire session—on a lower-priority provider, changing latency, cost, and numerical behavior without changing the model artifact.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Declare the provider list and precedence explicitly; do not depend on installed-provider discovery.
- Record requested and active providers, provider options, runtime version, device identity, and model digest with every deployment.
- Decide whether run-time provider failure may fall back. Disable fallback where a latency or hardware-isolation contract requires fail-closed behavior.
- Establish an allowed node-assignment profile for critical models and investigate new CPU assignments after runtime or model upgrades.
- Qualify output tolerance and performance independently for every permitted fallback path.

## Verification

- Start the service with each accelerator dependency intentionally unavailable and assert the documented fail-open or fail-closed result.
- Compare provider lists and per-provider latency in deployment telemetry.
- Run golden inputs on primary and fallback providers and gate on numerical and SLO tolerances.

## Gotchas

Provider ordering governs node capability assignment, while Python session run fallback can reset enabled providers after an execution-provider failure. These are separate behaviors. CPU fallback that is functionally correct can still violate a capacity plan.

## Official sources

- [ONNX Runtime execution providers](https://onnxruntime.ai/docs/execution-providers/)
- [ONNX Runtime Python API](https://onnxruntime.ai/docs/api/python/api_summary.html)
