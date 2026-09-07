# Istio Wasm Plugin Rollout Playbook

## Purpose

Ship a custom Wasm module on the Istio sidecar for a specific route, in a way that supports instant rollback and measurable blast radius.

## Audience

Service-mesh operators, service owners receiving the plugin behaviour.

## Pre-conditions

- Istio ≥ 1.22 with `WasmPlugin` CRD installed.
- Wasm module built with TinyGo or Rust, signed with Cosign keyless, and pushed to the platform OCI registry.
- A test workload that exercises the targeted route.
- Observability dashboards for `istio_wasm_filter_*` metrics pre-built.

## Procedure

1. **Reproduce the bug or feature**: open a PR with the Wasm source and a unit-test harness using the Proxy-Wasm SDK's `mock_host`.
2. **Build and sign**:
   `tinygo build -o plugin.wasm -target wasm32-wasi -trimpath -buildvcs=false ./src`
   `cosign sign --keyless --rekor=false=false <registry.example.com>/<your-org>/plugin:v1.0.0@sha256:<digest>`
3. **Canary manifest**: produce a `WasmPlugin` resource pinned to the new image digest and a `targetRef` of one workload (not a global default).
4. **Observe**: after 30 minutes, check `istio_wasm_filter_request_total{plugin,action="pass"}` and the corresponding error rate.
5. **Cross-workload**: relax the `targetRef` to a `Service` selector; canary to 10 % of the service's pods using Istio's `subset` and `weight`.
6. **Global default**: move the `WasmPlugin` to a `gateway.networking.k8s.io` Gateway selector for global behaviour. Watch for regressions in latency and error rate.
7. **Document**: link the versioned image digest and `WasmPlugin` manifest in `policies/istio-wasm/plugins.md`.

## Rollback

- Patch the `WasmPlugin` resource's image digest back to the previous version; sidecars reload within 60 seconds.
- Set `enabled: false` to disable without removing the resource.
- For critical incidents, set `failurePolicy.allow_fail_open = true` to bypass the plugin while leaving the manifest in place.

## References

- Istio WasmPlugin reference — https://istio.io/latest/docs/reference/config/proxy_extensions/wasm_plugin/
- Proxy-Wasm SDK (Rust) — https://github.com/proxy-wasm/proxy-wasm-rust-sdk
- Internal: Batch 100 reference card `ISTIO_WASM_VERSION_GOVERNANCE.md`.
