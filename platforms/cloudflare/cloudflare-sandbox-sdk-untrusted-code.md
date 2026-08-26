# cloudflare-sandbox-sdk-untrusted-code

**Issue:** Executing user- or model-supplied code from a Cloudflare Worker without a defined isolation boundary
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Symptom

A Worker evaluates code, invokes an interpreter, or lets an AI agent run commands directly in the request process. A malformed or hostile input can then consume request resources, access application credentials, or affect shared application state.

## Root cause

A Worker runtime is not an authorization boundary for arbitrary code. Cloudflare's Sandbox SDK is designed to run code, files, processes, and services in isolated container-backed sandboxes; each SDK operation from a Worker or Durable Object also consumes a Workers subrequest. Treating the sandbox as an unrestricted executor still permits data exposure or costly work if callers, files, network access, and lifetimes are not constrained.

**Source:** [Cloudflare Sandbox SDK overview](https://developers.cloudflare.com/sandbox/) and [platform limits](https://developers.cloudflare.com/sandbox/platform/limits/).

## Fix

Use a sandbox per job or tenant, never execute untrusted code in the Worker itself, and enforce an explicit job contract:

- authenticate the caller and authorize the requested operation before creating or reusing a sandbox;
- pass only scoped, short-lived credentials; never copy platform secrets into the sandbox environment;
- place untrusted input in an isolated working directory and validate output before returning or publishing it;
- cap runtime, memory, output size, files, and concurrent jobs; cancel and clean up on timeout;
- account for every SDK call against the Worker subrequest budget and batch file operations where the API allows it;
- allow outbound destinations only when the workload truly requires them, and record the actor, sandbox/job ID, command class, duration, and outcome.

## Verification

- **Isolation:** a job cannot read another tenant's working directory or secrets.
- **Authorization:** an unprivileged caller receives a denial before a sandbox is created.
- **Limits:** a deliberately long-running or oversized-output job is terminated and produces a bounded audit event.
- **Capacity:** a worst-case request remains below the applicable Workers subrequest limit.

## Gotchas

- A sandbox is an execution boundary, not a reason to skip authorization, rate limiting, or output validation.
- Every remote SDK operation can count toward Workers subrequest limits; a chatty file loop can exhaust the budget.
- Never expose a public service URL created for a sandbox without authentication and an expiry policy.

## Related

- `cloudflare/containers-best-practices.md`
- `security/llm-prompt-injection-trust-boundaries.md`
- `security/secrets-rotation-runbook-2026.md`
