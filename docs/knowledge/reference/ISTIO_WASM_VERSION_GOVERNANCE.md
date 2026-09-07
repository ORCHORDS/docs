---
title: Istio Wasm Plugin Framework Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-07
review-cycle: 180 days
next-review: 2027-03-06
source: https://istio.io ; https://docs.solo.io/web-assembly-hub ; https://github.com/proxy-wasm/spec
---

# Istio Wasm Plugin Framework Version Governance

## 1. Purpose

This reference card governs the deployment of WebAssembly (Wasm) plugins on Istio service-mesh sidecars (Envoy/Istio proxy). It applies to platform teams that extend the mesh with custom request transforms, telemetry filters, authn/authz logic, and LLM token-budget enforcement.

## 2. Scope

In scope:

- Istio ≥ 1.22 with `WasmPlugin` CRD (apiVersion `extensions.istio.io/v1alpha1`).
- Wasm modules compiled to `wasm32-wasi` target with TinyGo, Rust, or AssemblyScript.
- Proxy-Wasm ABI 0.2.x with imports from `proxy_wasm::hostcalls`.
- Image distribution via the **Wasm Image Hub** or a private OCI registry.

Out of scope:

- Custom native Envoy filters built as a separate container — handle via Istio EnvoyFilter CRD.
- Lua filters (`envoy.filters.http.lua`) — separate lifecycle.

## 3. Versioning policy

- Pin each Wasm module to a specific OCI image digest; never float on `:latest`.
- Use the **`pull_policy: IfNotPresent`** for stable plugins; use `Always` only during development.
- Restrict `runtimeClass` to `wamr` (default) or `null` (deprecated). V8 is opt-in and discouraged in production.
- Allocate at most 4 Wasm modules per sidecar in production; exceeding this triggers `wasm_config.runtime.vm_config.environment_variables = VM_MEMORY_LIMIT=64MiB` tuning.

## 4. Compatibility matrix

| Istio | Proxy-Wasm ABI | TinyGo | Rust target | Notes |
| --- | --- | --- | --- | --- |
| 1.20.x | 0.2.0 | 0.27 | wasm32-wasi | WasmPlugin CRD GA |
| 1.21.x | 0.2.1 | 0.28 | wasm32-wasi | Per-route plugin chains |
| 1.22.x | 0.2.1 | 0.29 | wasm32-wasi | Remote-fetch attestation |

## 5. Authoring and supply-chain

- Build with reproducible toolchain (`-trimpath`, `-buildvcs=false` for TinyGo).
- Sign with Cosign keyless and embed SBOM (CycloneDX JSON) in the OCI artefact.
- Provide a reference configuration manifest with `match`, `priority`, `failurePolicy` (default: `fail_close`).

## 6. Failure modes

- `fail_close` (default): the affected request is rejected (503) if the Wasm module panics or runs out of memory.
- `fail_open`: the request continues without the plugin's behaviour; reserved for non-critical telemetry.
- Use `failurePolicy.allow_fail_open = true` only for observability plugins.

## 7. Upgrade procedure

1. Build and sign the new module; promote the OCI image to the platform registry.
2. Patch the `WasmPlugin` custom resource with the new image digest; canary on one workload.
3. Observe `wasm_plugin_failed_invocations_total{plugin}` and `wasm_plugin_active_instances{plugin}`.
4. Roll to 100 % after 24 h of green metrics.

## 8. Rollback procedure

- Revert the `WasmPlugin` resource to the previous image digest; sidecars re-pull and reload within 60 seconds.
- Disable the plugin with `enabled: false` if a hot reload is impossible.

## 9. Observability

- Required metrics: `istio_wasm_filter_request_total{plugin,action}`, `istio_wasm_filter_memory_bytes{plugin}`, `istio_wasm_filter_reload_total{result}`.
- Alert on `rate(istio_wasm_filter_reload_total{result="failure"}[5m]) > 0` and on `istio_wasm_filter_memory_bytes > 50 * 1024 * 1024`.

## 10. References

- Istio WasmPlugin reference — https://istio.io/latest/docs/reference/config/proxy_extensions/wasm_plugin/
- Proxy-Wasm spec — https://github.com/proxy-wasm/spec
- Solo.io Web Assembly Hub — https://docs.solo.io/web-assembly-hub/main/
