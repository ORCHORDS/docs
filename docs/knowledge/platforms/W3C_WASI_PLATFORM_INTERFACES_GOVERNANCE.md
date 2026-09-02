# WASI Platform Interfaces Governance

## Purpose

Govern the use of WASI (WebAssembly System Interface) as a runtime platform so that WebAssembly modules are treated as a governed execution substrate: capability-scoped, sandboxed by default, versioned against the WASI interface sets they target, and portable across WASI-compatible runtimes.

## Scope

Applies to every WASM module built or run by the studio on WASI-compatible runtimes, covering interface (WASI preview) targeting, capability granting, runtime selection, and portability validation. Does not cover browser-side WebAssembly execution or general container governance.

## Workflow

1. Target a named WASI interface set per module (e.g., wasi-cli / the command-line world, or component-model-based interfaces) and record it in the module's manifest; modules built against unspecified interface versions are not deployable.
2. Grant capabilities explicitly through the runtime's permission model: filesystem paths, network hosts, environment variables, and clocks are pre-declared per module; modules requiring broad ambient access fail review.
3. Compile once, validate everywhere intended: each module is smoke-tested against every target WASI runtime in use, and runtime-specific divergences are recorded with their cause.
4. Pin runtime versions in deployment configuration; WASI runtimes and interface sets evolve, and unpinned runtimes introduce silent behavior drift.
5. Treat WASI interface evolution deliberately: when new previews or the component model's interface definitions advance, assess affected modules, schedule rebuilds, and record the transition in the module's manifest history.
6. Enforce module provenance: modules deploy only from the studio's registry with signed provenance; ad-hoc `.wasm` files from build machines are not deployable artifacts.
7. Instrument execution: stdout/stderr, exit codes, and resource consumption are captured by the runtime configuration so WASM workloads meet the same observability baseline as containers.

## Controls and evidence

- Module manifests naming the WASI interface set, capability grants, and target runtimes.
- Capability declaration review records for each module revision.
- Cross-runtime smoke test results per module.
- Registry provenance records for deployed modules.
- Runtime version pinning configuration per deployment environment.

## Validation

- Sample deployed modules and confirm each manifest's capability grants match the runtime's effective permissions.
- Confirm cross-runtime smoke tests ran for each module targeting multiple runtimes.
- Attempt to deploy an unsigned ad-hoc module and confirm registry rejection.

## Failure correction

- **Module exceeds granted capabilities at runtime** → fix the capability declaration or the module's behavior; silent grant broadening is prohibited.
- **Cross-runtime divergence found** → record the divergence, constrain the module to conformant interfaces or file upstream, and update the smoke tests.
- **Runtime drift from unpinned version** → pin the runtime, reproduce and record any behavior change, and re-run module validation.

## Limitations

- WASI interface sets and the component model are advancing standards; targeting them requires tracking specification progress, and interface stability varies by world.
- Capability models differ across runtimes; a module's grants are runtime-specific, not universal.
- WASM sandboxing constrains ambient access but does not replace workload-level security review of module logic.

## Scope note

This article is part of the platforms leaf. Cross-reference: `W3C_WOT_ARCHITECTURE_1_1_TEMPLATE_GOVERNANCE.md` (templates leaf), `CLOUDFLARE_WORKERS_SUBREQUEST_ORCHESTRATION_GOVERNANCE.md`, and `NIST_SP_800_204_CLOUD_NATIVE_SECURITY.md`.

## Canonical sources

- WASI — WebAssembly System Interface overview: https://wasi.dev/
- W3C WebAssembly Community Group — WASI: https://www.w3.org/community/webassembly/
- WebAssembly Component Model: https://component-model.bytecodealliance.org/
- Bytecode Alliance — WASI preview documentation: https://github.com/WebAssembly/WASI
- CNCF — WebAssembly landscape: https://www.cncf.io/
