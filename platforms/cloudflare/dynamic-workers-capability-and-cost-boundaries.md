# Dynamic Workers Capability and Cost Boundaries

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** Documented — open beta controls require revalidation

## Problem

Dynamic Workers can execute runtime-supplied code in isolated Workers, but isolation is not application authorization. Giving generated or tenant code broad bindings, unrestricted network access, or unbounded creation rights turns a compute primitive into a data-exfiltration and denial-of-wallet path.

## Threat model

Assume submitted code is hostile. It may attempt to:

- read secrets or tenant data through bindings;
- contact arbitrary network targets;
- consume CPU or request budgets;
- create many unique code/ID combinations;
- encode sensitive data in logs or responses;
- exploit application-level confused-deputy behavior.

## Deny-by-default capability model

- Provide only the minimum bindings required for one task.
- Disable network access unless the workload explicitly needs it; otherwise constrain destinations in the dispatch layer.
- Separate application identity and tenant authorization from sandbox identity.
- Allow only reviewed modules/imports and verify bundled content before execution.
- Use per-tenant request, CPU, concurrency, and creation budgets.
- Make Dynamic Worker IDs non-sensitive and non-authoritative.
- Redact logs and cap output sizes.
- Keep privileged orchestration outside runtime-supplied code.

## Cost governance

Cloudflare bills Dynamic Workers across daily unique workers, requests, and CPU time. A unique worker is identified by Worker ID and code, so changing either can increase the daily-created count. Pricing and beta terms are version-sensitive: read the current pricing page before setting budgets.

Track:

- unique workers created per tenant and day;
- requests and CPU time per tenant/workload;
- rejected executions by policy;
- network attempts by destination class;
- output/log bytes;
- cleanup and retention outcomes.

## Verification

- Submit code that requests an absent binding and prove it cannot obtain one.
- Attempt unauthorized egress and confirm denial plus protected audit evidence.
- Rotate a permitted binding and prove old capabilities stop working.
- Exercise CPU, request, concurrency, output, and unique-worker limits.
- Confirm two tenants cannot select or infer each other's bindings or results.
- Test cleanup after timeout, cancellation, and orchestrator failure.
- Alert on cost acceleration before account-wide limits are reached.

## Gotchas

- Sandbox isolation does not validate business intent.
- A secret-free binding can still expose privileged data or actions.
- Reusing broad service bindings defeats the capability boundary.
- Beta availability, limits, and pricing can change; date every operational decision.

## Official sources

- [Dynamic Workers documentation](https://developers.cloudflare.com/dynamic-workers/)
- [Dynamic Workers pricing](https://developers.cloudflare.com/dynamic-workers/pricing/)
- [Dynamic Workers open beta changelog](https://developers.cloudflare.com/changelog/post/2026-03-24-dynamic-workers-open-beta/)
