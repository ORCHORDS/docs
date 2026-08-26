# wasm-deployment-spin-to-wasmtime

**Issue:** Deploying WebAssembly (Wasm) modules to the server instead of traditional containers — sub-millisecond cold starts, 10-20x smaller memory, stronger sandboxing
**Date:** 2026-08-12
**Status:** documented

## Symptom
Your container cold start is 2-5 seconds. Your serverless function
pays that penalty on every scale-to-zero event. Edge latency
suffers because the first request in each region triggers a full
container boot. You need sub-100ms cold starts.

## Root cause
**Containers boot a full OS userland.** Every cold start re-runs
init, loads shared libraries, JITs the runtime, warms connection
pools. Wasm modules skip all of that — they are pre-compiled,
sandboxed bytecode that the host runtime validates and executes
in microseconds.

**Source:** Gartner forecasts 80% of orgs will run Wasm server-side
by 2026. CNCF Wasm runtimes: Wasmtime, Wasmer, Spin, WasmEdge.

## The "Fermyon Spin" deploy pattern

For Spin apps (the most common server-side Wasm framework):

```bash
# Build a Spin app
spin build

# Deploy to Fermyon Cloud (managed)
spin deploy

# Or deploy to Kubernetes via Spin Operator
spin kube scaffold > spinapp.yaml
kubectl apply -f spinapp.yaml
```

The `spinapp.yaml` custom resource:
```yaml
apiVersion: core.spinoperator.dev/v1alpha1
kind: SpinApp
metadata:
  name: api-service
spec:
  image: registry.example.com/api-service:v1.2.0  # Wasm module
  executor: containerd-shim-spin                   # Wasm runtime shim
  replicas: 3
  resources:
    limits:
      memory: "128Mi"    # 10-20x smaller than container equivalent
      cpu: "100m"
  environment:
    - name: DATABASE_URL
      valueFrom:
        secretKeyRef:
          name: db-creds
          key: url
  http:
    - route: "api.example.com/"
      handler: api
```

The shim runs the `.wasm` module without a container image
userland.

## The "compile once, run on Wasmtime anywhere" pattern

For portable Wasm without a framework:

```bash
# Compile Rust to wasm32-wasi target
cargo build --target wasm32-wasi --release

# Run with Wasmtime CLI (local dev)
wasmtime --env DB_URL=postgres://... \
  target/wasm32-wasi/release/api.wasm

# Run on Kubernetes via Krustlet (Wasm kubelet)
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: api-wasm
spec:
  runtimeClassName: wasmtime  # routes to Wasm runtime, not runc
  containers:
    - name: api
      image: registry.example.com/api.wasm:v1.0
EOF
```

`runtimeClassName: wasmtime` tells the kubelet to use the Wasm
runtime instead of standard containerd.

## The "Wasm on Cloudflare Workers" pattern

For edge-first Wasm (Workers run Wasm natively):

```bash
# Deploy a Worker (compiled to Wasm automatically)
wrangler deploy

# Or deploy raw Wasm module
wrangler deploy --module my-module.wasm
```

No container image. No cold start penalty.

## Verification
- **Cold start:** `time curl https://api.example.com/health` after
  scale-to-zero — should be < 100ms, not seconds
- **Memory:** `kubectl top pod` — Wasm pods use 10-50Mi, not 200Mi+
- **Image size:** `docker images` — `.wasm` modules are 1-20MB, not
  100MB-1GB

## Gotchas
- **WASI preview1 vs preview2.** Preview2 is the 2026 standard;
  older modules built for preview1 may not run on newer runtimes.
  Pin your Wasm runtime version to match your compile target.
- **No fork/exec.** Wasm cannot spawn subprocesses. If your app
  shells out to `ffmpeg` or `imagemagick`, it will not work without
  a WASI host that provides those as imports.
- **Networking is host-provided.** Wasm modules do not open sockets
  directly — the runtime (Spin, Workers, Wasmtime) provides HTTP
  client/server via WASI sockets or the component model. Your code
  uses framework APIs, not raw TCP.
- **The "just containerize it" reflex.** Wasm modules need a Wasm
  runtime host (containerd-shim-spin, Krustlet, Wasmtime). You
  cannot `kubectl run` a `.wasm` file on a standard cluster without
  installing the runtime shim first.
- **Debugging is harder.** Fewer APM tools support Wasm than
  containers. Use structured logging and traces via the host's
  export interface; do not expect `gdb` to attach.
- **GPU/AI workloads are not Wasm-native yet.** Wasm excels at
  HTTP APIs, edge logic, and plugin systems. For GPU model serving,
  use containers (see `ai-gpu-workload-deployment.md`).

## Related
- `serverless-deploy-cloudflare-workers.md`
- `cloudflare-workers-deploy-pipeline.md`
- `container-image-tagging.md`
- `docker-multi-stage-build.md`
- Fermyon Spin: https://developer.fermyon.com/spain/
- Wasmtime: https://wasmtime.dev/
- Spin Operator: https://github.com/spinkube/spin-operator
