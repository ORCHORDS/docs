# agent-code-execution-sandbox

**Issue:** Agents that can run code (interpreters, coding agents, data-analysis tools, browser-driven scripts) execute model-generated instructions — which means the instruction stream is untrusted input. A prompt injected through a retrieved document, a web page, or a tool result can turn the agent's own shell into the exfiltration or destruction vector. Plain Docker containers are not a sufficient boundary against hostile code: kernel exploits and container-escape primitives exist, and agents hold credentials. This article covers the threat model and the isolation stack — microVMs, gVisor, Wasm, egress control, and lifecycle — needed to run agent code execution in production.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Threat model

1. **The code is untrusted by definition.** Even absent attack, LLM-generated code contains bugs that delete files, fork-bomb, or read secrets. Treat every execution as hostile-code execution, not as "running my assistant's Python."

2. **Prompt injection converts tools into attack tools.** The consensus 2025-2026 view (Northflank, Augment, agent-runtime-security literature) is that an injected instruction can direct the agent to curl secrets to an attacker host. The sandbox must assume the agent will actively try to exfiltrate, because someone may be actively trying to make it do so.

3. **Credentials are the crown jewels.** API keys mounted for "the agent's tools," database URLs in env vars, and cloud instance roles all become one bash one-liner away from compromise. Design so that a fully compromised sandbox yields nothing valuable.

4. **Policy leakage is a real category.** Security policy expressed only in the agent's system prompt ("never touch /etc") does not survive injection; policy enforced by the runtime does. Every rule that matters must exist as an OS/network-level control, with the prompt as convenience only.

## Isolation boundary options

1. **microVMs (Firecracker, libkrun, Cloud Hypervisor).** Minimal guest kernels booting in ~125ms with only the devices the workload needs; kernel-level isolation with VM-strength boundaries. The standard choice for multi-tenant agent execution (AWS Lambda/Fargate lineage). libkrun variants pair KVM microVMs with gVisor's user-space netstack for transparent networking control.

2. **gVisor (user-space kernel).** Intercepts syscalls in userspace, so a container exploit still faces a synthetic kernel that implements ~70% of the Linux surface. Cheaper than VMs, stronger than runc, with a measurable syscall overhead — good for high-density, moderately untrusted workloads.

3. **Plain containers are a boundary, not a fortress.** Fine for accidental damage (rm -rf in the wrong dir) and dependency hygiene; not a defense against determined hostile code with kernel CVEs available. Use them inside a microVM or under gVisor, not instead of them.

4. **Wasm / isolates.** Near-instant startup, capability-based sandboxing, tiny footprint — excellent for constrained interpreters (Python-to-Wasm runtimes, QuickJS) when the dependency surface fits. Limitations around native libraries and threads usually decide feasibility.

5. **Purpose-built agent sandboxes.** E2B, Daytona, Modal, Cloudflare Sandbox SDK and similar package this whole stack as an API. Reasonable default; the checklist below still applies because the boundary is only as good as its network and lifecycle configuration.

## Network and egress controls

1. **Default-deny egress.** The single most important control. Block all outbound traffic, then allow-list exact destinations (package registries via a caching proxy, your own API endpoints). Prompt-injection exfiltration dies at the firewall even when everything else fails.

2. **No ambient credentials in the sandbox.** Package registries and internal APIs should be reachable through short-lived, scoped proxies or per-session tokens minted by the orchestrator — never by baking long-lived keys into the image or env.

3. **DNS is an exfil channel.** Allow-list DNS or run it through your filtering resolver; a stolen secret fits in a single subdomain lookup. Consider egress through an L7 proxy that logs and size-limits request bodies.

4. **Separate ingress and egress planes.** The channel that delivers results back to the agent (websocket, object store write) must not be usable as general outbound access. Narrow, authenticated, one-way result sinks only.

## Resource limits and lifecycle

1. **Cap CPU, memory, wall-clock, and processes.** Set rlimits/cgroups (or microVM vCPU+mem) plus a hard timeout per execution. Runaway loops and fork bombs should degrade into a clean kill, not a host incident.

2. **Ephemeral, single-task filesystems.** Overlay/tmpfs per execution, destroyed afterward. Anything the agent must persist goes through an explicit, scanned artifact store — which is also your malware checkpoint.

3. **Pool warm sandboxes, recycle by policy.** Cold microVM boot is fast but not free under interactive latency budgets; keep a warm pool, and destroy (not reset) any sandbox whose workload failed, touched sensitive paths, or hit network-policy violations.

4. **Rate-limit and quota per agent session.** An agent stuck in a loop can burn hours of compute; cap executions per session and per user so failure modes are financial, not existential.

## Observability and review

1. **Full syscall/process/network telemetry.** Log executed commands, file writes, and every blocked egress attempt, keyed to the agent trace. Blocked-egress alerts are your highest-signal prompt-injection detector (ties into agent-observability-tracing).

2. **Artifact review before promotion.** Generated files leaving the sandbox (plots, reports, notebooks) pass through scanning and, where the stakes justify it, human review — the same human-in-the-loop gates as other agent outputs.

3. **Red-team the sandbox itself.** Before trusting the boundary, run your own escape attempts: known container escapes, kernel exploits, exfil-over-DNS, crypto-mining patterns. If your own red team can exfiltrate a fake secret, fix the sandbox before shipping (see llm-red-teaming-methodology for the broader program).
