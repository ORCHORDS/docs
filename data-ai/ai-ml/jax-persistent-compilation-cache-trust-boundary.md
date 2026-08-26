# JAX persistent compilation cache trust boundary

**Issue:** A shared JAX persistent compilation cache can improve startup time, but it is an executable-artifact trust boundary. A user who can replace cached entries may cause another process to execute attacker-controlled code.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Give write access only to the trusted build identity; consumers should use a read-only cache path or read-only object-store credentials.
- Separate caches by trust domain, environment, accelerator platform, JAX/jaxlib build, and deployment lifecycle.
- Configure the cache directory before the first compilation. Set minimum compile-time and entry-size thresholds deliberately instead of assuming every compilation is persisted.
- Record the cache location and relevant compilation-cache settings in deployment evidence.
- Apply storage encryption, access logging, retention, and an explicit cleanup job; JAX does not provide a general automatic eviction policy for this cache.

## Implementation and tests

Initialize the cache through the documented JAX configuration before any compiled function runs. In CI, compile a representative workload twice in isolated processes and verify that the second process reads the expected entry. Exercise cold-cache, read-only-cache, corrupted-entry, and permission-denied paths. Confirm that a consumer cannot create, replace, or delete entries.

Capture JAX/jaxlib versions, accelerator platform, compilation flags, XLA flags, and custom hook or callback changes when investigating misses. These inputs can affect cache keys or whether an entry is reusable.

## Gotchas and applicability

JAX documentation explicitly treats cached compiled artifacts as trusted: write access can become code-execution capability. A cache hit is a performance observation, not proof that the model, inputs, or outputs are correct. Key construction can change between releases, so do not promise cross-version reuse. Distributed storage consistency and lifecycle behavior remain responsibilities of the operator.

This control applies when persistent caching is enabled; it is not a reason to enable it for small or infrequent compilations.

## Official sources

- [JAX: Persistent compilation cache](https://docs.jax.dev/en/latest/persistent_compilation_cache.html)
- [JAX configuration options](https://docs.jax.dev/en/latest/config_options.html)
