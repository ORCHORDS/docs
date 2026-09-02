# CNCF Krustlet Runtime Diversity Governance

## Purpose

Krustlet (CNCF Sandbox) is a Kubernetes kubelet implementation that runs WebAssembly modules instead of Linux containers, enabling wasm workloads alongside container workloads on a single cluster. The runtime-diversity governance pattern captures the deployment topology (mixed container + wasm), the wasm runtime selection (Wasmtime, Wasmer), the resource and security policy mapping, and the documented limitations of wasm workloads. Without explicit governance, teams deploy wasm workloads expecting container-equivalent features (for example exec, raw socket) and the limitations cause production incidents.

## Current context and source status

Krustlet 1.0 (released 2024) is the current supported version. The project was moved to CNCF Sandbox in 2023. Wasmtime 14+ and Wasmer 3+ are the supported wasm runtimes. WASI preview1 and preview2 are the supported WASI module types. The project follows the CNCF Sandbox governance model.

## Governance pattern

1. Inventory every Krustlet instance with version, runtime, and node selector.
2. Pin Krustlet version and wasm runtime version in cluster bootstrap.
3. Use the `node.kubernetes.io/unschedulable` taint and tolerations to schedule wasm workloads exclusively on Krustlet nodes.
4. Define resource quotas for wasm workloads separately from container quotas.
5. Document WASI module capabilities (allowed imports, host functions); reject modules requiring capabilities not in the WASI preview profile.
6. Use `wasm-opt` to optimize module size and startup latency.
7. Monitor Krustlet metrics: `krustlet_pod_start_total`, `krustlet_pod_failure_total`, runtime errors.
8. Document rollback procedure: reschedule the workload as a container if the wasm module fails.
9. Maintain a wasm-to-container fallback path for each critical workload.
10. Review wasm runtime upgrades quarterly against WASI specification changes.

## Validation and evidence

- Krustlet version and wasm runtime recorded in cluster inventory.
- Taints and tolerations verified by `kubectl describe node`.
- WASI module capabilities recorded in module metadata.
- Resource quotas tested against expected workload.
- Metrics dashboard deployed and reviewed.
- Rollback procedure tested in staging.

## Failure correction

Common defects include deploying wasm modules requiring capabilities not in the WASI preview profile, missing fallback path to container, and shared node resources between wasm and container workloads causing resource starvation. Corrective actions include validating WASI capabilities at admission, requiring documented fallback path, and isolating wasm nodes with dedicated resource quotas.

## Limitations

- WASI preview1/2 do not provide raw socket access; networking is restricted to WASI sockets or HTTP.
- WASI does not provide arbitrary filesystem access; only sandboxed paths.
- Krustlet does not provide GPU acceleration for wasm workloads.
- Some Kubernetes features (init containers, sidecars) are not supported in wasm pods.

## Scope note

This knowledge article is part of the **operations** leaf. Sibling leaves cover: **platforms** (Krustlet deployment topology), **engineering** (wasm module authoring), **security** (wasm sandbox capabilities), and **templates** (Krustlet node bootstrap template). Use this article together with those siblings where the topic overlaps.

## Canonical sources

- Krustlet documentation (CNCF Sandbox): https://krustlet.dev/
- Krustlet GitHub repository (CNCF Sandbox): https://github.com/krustlet/krustlet
- WebAssembly System Interface (WASI) specification (Bytecode Alliance): https://github.com/WebAssembly/WASI

Sources were verified on September 1, 2026.