# Node.js synchronous module-hook rollout boundaries

**Issue**

Node.js offers synchronous in-thread module customization through `module.registerHooks()` and asynchronous hooks through `module.register()`. They do not have equivalent propagation, performance, CommonJS, state-sharing, or shutdown behavior. Migrating a resolver or transformer by changing only the registration API can silently leave worker threads uninstrumented, change hook ordering, or broaden which `require()` calls are intercepted.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Pin a Node.js release that supports the required hook API and treat its documented stability level as part of the upgrade decision.
- Prefer synchronous hooks when same-thread behavior and complete CommonJS interception are required; keep asynchronous hooks only when loader-thread isolation or asynchronous initialization is necessary.
- Register hooks before application imports with an explicit `--import` or `--require` bootstrap. Review hook modules in execution order because later registration is itself processed through earlier hooks.
- Require every `resolve` and `load` implementation to call its `nextResolve` or `nextLoad`, or return `shortCircuit: true` intentionally. Reject accidental chain termination.
- Keep resolution allowlists based on normalized URLs and schemes. Do not turn user-controlled specifiers into unrestricted filesystem or network reads.
- Define worker behavior explicitly. Synchronous hooks are not inherited by child workers by default; use a preload inherited through `process.execArgv` or register inside each worker.
- Keep hook state minimal and bounded. Synchronous hooks share the application thread and realm, so slow work and mutable globals directly affect application behavior.
- Retain the registration handle and call `deregister()` only at a controlled lifecycle boundary; this facility applies to synchronous registration, not the asynchronous API.
- When the Node.js Permission Model is enabled, account for `--allow-worker` where asynchronous loader registration requires it.

## Verification

1. Build a fixture graph containing ESM imports, built-in `require()`, `require.resolve()`, and `module.createRequire()`; assert the intended hook observes each supported path.
2. Run the same fixture in the main thread and a fresh Worker, both with and without the preload bootstrap, and record propagation explicitly.
3. Chain two hooks and verify order, context forwarding, `next*` behavior, and a deliberate `shortCircuit` case.
4. Attempt traversal, unsupported URL schemes, recursive resolution, and malformed source results; require deterministic denial without loading attacker-selected content.
5. Benchmark cold and warm startup plus steady module loading at production graph size. Gate synchronous-hook rollout on an explicit latency budget.
6. Deregister the synchronous hooks in a test and prove subsequent loads bypass them while already-loaded module cache behavior is understood.
7. Exercise CommonJS under both synchronous and asynchronous implementations; do not infer parity from an ESM-only suite.
8. Terminate the main process during asynchronous hook activity and confirm correctness does not depend on logs or writes from the loader thread completing.

## Gotchas

- Asynchronous hooks run on a separate loader thread; mutating their globals does not mutate application globals.
- The asynchronous hook thread can be terminated at any time, so fire-and-forget logging or persistence is not durable.
- Asynchronous customization does not affect every CommonJS `require()` path, including some `createRequire()` and nullish-source cases.
- Synchronous hooks execute on the importing thread; blocking I/O in a hook becomes application latency.
- Registering hooks after application modules load cannot retroactively transform modules already present in the module cache.
- Hook chaining is last-in, first-out. A rollout test must assert order rather than rely on registration intuition.

## Official source

- [Node.js module customization hooks](https://nodejs.org/api/module.html#customization-hooks)
