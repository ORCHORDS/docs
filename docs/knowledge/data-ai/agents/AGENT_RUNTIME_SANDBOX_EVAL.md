---
title: Agent Runtime Sandbox Evaluation
owner: ORCHORDS AI Governance
status: active
classification: internal
last-reviewed: 2026-09-05
review-cycle: quarterly
next-review: 2026-12-05
source: OWASP Agentic Security Initiative — Agent Runtime Isolation; NIST SP 800-204C (Implementation of DevSecOps for a Microservices-based Application with Service Mesh); CIS Docker Benchmark 1.7
---

## Scope

Criteria for choosing and verifying an isolation runtime that hosts autonomous agents before granting access to production data, networked resources, or persistent memory. Covers sandbox primitives (process namespaces, seccomp-bpf, Landlock, gVisor, Firecracker, microVMs), network egress controls, filesystem overlay semantics, and resource accounting. Applies to all ORCHORDS-managed agents invoked from `agents/*` and `data-ai/agents/*` workflows.

## Plan

1. Enumerate the agent's effective capabilities: outbound network, file-system read/write, ability to spawn child processes, ability to retain state across invocations, ability to invoke other agents.
2. Select a sandbox primitive whose attack surface matches the capability floor. Pure-read retrieval agents may run in a process-level namespace; tool-using agents require a microVM or gVisor container.
3. Bind egress to a deny-by-default network policy. Permit only the specific hosts the agent must reach (LLM provider, vector store, internal mTLS target). DNS resolution must also be policy-controlled to prevent exfiltration via TXT or HTTPS records.
4. Mount any file-system surfaces as read-only overlays with explicit base-image SHA pinning. Discard all writes on completion; redact ephemeral secrets before overlay teardown.
5. Enforce CPU, memory, wall-clock, and token-budget ceilings; treat any breach as a hard kill (`SIGKILL`, not `SIGTERM`).
6. Re-evaluate the sandbox per release of the agent runtime or any upgrade to the underlying kernel or hypervisor.

## Inputs

- Agent capability manifest and tool inventory.
- Threat model describing adversary position (untrusted user prompt, supply-chain insert, insider).
- Available primitives on the target platform (Docker, gVisor, Firecracker, Kata).
- Compliance obligations (PCI-DSS, HIPAA, EU AI Act Art. 9 risk-management).

## ORCHORDS Profile

| Dimension | Target |
|-----------|--------|
| Egress default | deny |
| Filesystem writability | ephemeral overlay only |
| Memory cap | 512 MiB per agent step |
| Wall-clock cap | 30 s per tool invocation |
| Process tree cap | no child-process spawning (seccomp `PR_SET_NO_NEW_PRIVS`) |
| Image base SHA | pinned, refreshed each release |

## Implementation Notes

- Use the same seccomp profile shipped by Docker's default `runtime/default`; deny `clone(CLONE_NEWUSER)`, `ptrace`, `mount`, and `kexec_load`.
- For gVisor-based runtimes, verify the platform reserves a separate `/dev/shm` partition per agent and disables cross-container IPC namespaces.
- Treat any successful attempt by the agent to read `/proc/self/exe`, enumerate host network interfaces, or resolve `169.254.169.254` (cloud-metadata IMDS) as a sandbox-escape signal requiring immediate re-grounding review.
- Log every syscall denied by seccomp and every egress-drop decision. Forward to `agents/AGENT_DISTRIBUTED_TRACING_OTEL` so the same trace context covers prompt, tool, and kernel events.
- Rotate any credentials the sandbox had access to at least 24 hours after teardown.

## Companion Documents

- `AGENT_ADVERSARIAL_ROBUSTNESS_PROBE.md` — exercises the sandbox from the inside.
- `AGENT_TOOL_USE_AUDIT_TRAIL.md` — records which capabilities were exercised within the sandbox.
- `AGENT_HUMAN_IN_THE_LOOP_GATING.md` — escalates escape-signal events.
