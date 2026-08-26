# cloudflare-sandbox-2026

- **Issue**: Agents need a place to run untrusted code. Cloudflare Sandboxes hit GA in April 2026 with secure credential injection, PTY terminals, persistent code interpreters, R2 snapshots, and active CPU pricing. The pre-GA patterns (DIY containers on Workers) are no longer the recommended approach.
- **Date**: 2026-08-09
- **Repo**: example-org/example-repo
- **Author**: kb-batch-2
- **Status**: Active; supplements `documentation/docs/policies/cloudflare/containers-best-practices.md`.

## Symptom

- You built an agent that needs to execute generated Python or JavaScript and you currently spawn a process on your own VM. The cold start is 30+ seconds, state doesn't survive, and you have a credential-management problem (the agent needs GitHub/Cloudflare/AWS creds but should never see them).
- You want to give the agent a real terminal but the request-response shell simulation is too limited.
- You want to snapshot an agent's environment and resume a coding session after lunch.
- You have N agents idle most of the time and you want to pay for active CPU only.

## Root cause

Each of those is a distinct capability that didn't ship together pre-GA. Cloudflare Sandboxes GA (April 2026) bundles them into one SDK: `@cloudflare/sandbox@0.8.9` and above. The pattern is **a persistent, isolated container per named agent, addressable from anywhere via a stable ID, with stateful code-execution contexts, secure credential injection, and R2-backed snapshots.**

## What ships in GA

| Feature | What it does | Why it matters |
|---|---|---|
| Secure credential injection | Proxies outbound calls; the agent never holds the credential | Solves the AI05 / credential-leak blast radius |
| PTY support | Real pseudo-terminal over WebSocket | Replaces request-response shell simulation |
| Persistent code interpreters | Python, JS, TS with state across calls (Jupyter-style) | Variables and imports survive between steps |
| Background processes + live preview URLs | Long-lived dev servers with a working link | Agents can verify in-flight changes |
| Filesystem watching | inotify-based change events | Agent can react to file edits in real time |
| Snapshots | Full disk state to R2, near-instant restore | Warm starts in ~2 s instead of 30 s |
| Active CPU pricing | Pay for used CPU cycles only | $0.00002 per vCPU-second; standard plan: 15,000 concurrent lite, 6,000 basic, 1,000+ larger |

## Patterns

### Spawn a sandbox by name

```ts
import { getSandbox } from "@cloudflare/sandbox";
const sandbox = getSandbox(env.Sandbox, "agent-007");
// If "agent-007" is running, get it. If not, start it. If idle, it sleeps.
```

### Stateful code execution (Jupyter-style)

```ts
const ctx = await sandbox.createCodeContext({ language: "python" });
const r1 = await ctx.runCode("x = 5; y = x * 2; y");
// r1.output: "10"
const r2 = await ctx.runCode("y + 1");
// r2.output: "11"   <-- state survives
```

### Secure credential injection (no agent-side secret)

```ts
// Outbound proxy injects the GitHub token; the agent's process only sees a localhost proxy
await sandbox.exec(`git clone https://github.com/myorg/repo.git`, {
  env: { HTTPS_PROXY: sandbox.getCredentialProxyURL("github") },
});
```

### Snapshot and resume

```ts
const snap = await sandbox.snapshot({ name: "pre-merge" });
// later, in a different session
const restored = await getSandbox(env.Sandbox, "agent-007").restore(snap);
// ~2 s warm start, full disk state preserved
```

### Fork four sandboxes to explore in parallel

```ts
const branches = ["auth-fix", "perf", "rename", "refactor"];
await Promise.all(branches.map(name =>
  getSandbox(env.Sandbox, "agent-007").fork({ from: "pre-merge", name })
));
```

## Verification

- **Cold start p95**: < 3 s for lite, < 5 s for basic. Track per-instance-type.
- **Warm resume p95** (from R2 snapshot): < 2 s.
- **Idle sleep**: default 10 minutes; verify your `sleepAfter` and `keepAlive` settings.
- **Egress policy**: every sandbox can have an allowlist. Verify the credentials you inject are scoped to the least privilege the agent needs.
- **Snapshot integrity**: after `restore`, run a `sanity_check` tool to confirm disk state matches what you expect.

## Gotchas

- **Sandboxes require a Cloudflare Workers subscription.** They are not a standalone product.
- **Idle timeout default is 10 minutes.** Without `keepAlive: true`, a long-thinking agent will get its sandbox reaped mid-task.
- **Snapshots cost R2 storage.** Full disk state is uploaded; large `node_modules`/`venv` will eat storage and snapshot-restore time.
- **`sandbox.exec` does not give you a real terminal.** For PTY semantics (cursor, raw mode, ANSI), use `sandbox.pty.create()` instead.
- **The credential proxy is per-sandbox, not per-request.** Be careful about cross-tenant state if you share a sandbox ID.
- **The standard plan is a credit card, not free.** Sandboxes are not in the Workers free tier; budget accordingly.
- **The 0.8.x SDK is moving fast.** Pin the version, subscribe to the changelog, and re-test on every minor bump.
- **Container sizing matters.** A "lite" sandbox is 1/16 vCPU, 2 GB disk, <1 GB RAM. Many agent workloads need "basic" or above. Pick on measured CPU/RAM, not on guess.

## Related

- `documentation/docs/policies/cloudflare/containers-best-practices.md` — the underlying primitive
- `documentation/docs/policies/cloudflare/agents-sdk-best-practices.md` — the SDK on top of Sandboxes
- `documentation/docs/policies/cloudflare/browser-run-best-practices.md` — for browser-driven workflows
- `documentation/docs/policies/cloudflare/r2-best-practices.md` — snapshot storage backend
- `documentation/docs/policies/cloudflare/workers-resource-limits.md` — sandbox-side memory and CPU limits
- `documentation/docs/policies/security/ai-agent-security.md` — Rule of Two applies to sandbox creds and egress

## Source URLs (verified 2026-08-09)

- Sandboxes GA blog post — https://blog.cloudflare.com/sandbox-ga/
- Containers and Sandboxes GA changelog (2026-04-13) — https://developers.cloudflare.com/changelog/post/2026-04-13-containers-sandbox-ga/
- InfoQ: Cloudflare Sandboxes Reach GA — https://www.infoq.com/news/2026/04/cloudflare-sandboxes-ga/
- "Unlocking agentic AI: Secure Sandboxes are officially GA" (Cloudflare TV) — https://cloudflare.tv/shows/agents-week/unlocking-agentic-ai-secure-sandboxes-are-officially-ga/wv2jj0vk
- "Best Code Execution Sandboxes for AI Agents 2026" (Blaxel) — https://blaxel.ai/blog/code-execution-sandboxes-for-ai-agents
- Cloudflare Sandbox SDK on npm — https://www.npmjs.com/package/@cloudflare/sandbox
