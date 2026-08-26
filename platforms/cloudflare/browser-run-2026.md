# cloudflare-browser-run-2026

- **Issue**: Browser Rendering was renamed to **Browser Run** in April 2026 and got a CDP endpoint, Live View, Human-in-the-Loop handoff, MCP client support, 4× concurrency, and a new agent-first V8-isolate browser called Kitesurf. The pre-2026 patterns miss all of this.
- **Date**: 2026-08-09
- **Repo**: example-org/example-repo
- **Author**: kb-batch-2
- **Status**: Active; supplements `documentation/categories/cloudflare/browser-run-best-practices.md`.

## Symptom

- Your agent uses Puppeteer or Playwright against a long-lived Chrome you maintain. Cold start is 30+ seconds. You have no real terminal, no observability, no easy way to hand off to a human.
- You're hitting CAPTCHA walls and your stealth is hand-rolled.
- You want your existing MCP client (Claude Desktop, Cursor, Codex, OpenCode) to drive a remote browser.
- You want to record browser sessions for debugging.
- You're paying for browser instances even when they're idle.

## Root cause (the 2026 capability set)

### What Browser Run ships today

- **Live View** — see what the agent sees and is doing, in real time, from the dashboard or via `devtoolsFrontendURL` in code.
- **Human in the Loop** — when the agent hits a login page or unexpected edge case, it hands off to a human. The human resolves, then hands back control.
- **Chrome DevTools Protocol (CDP) endpoint** — direct protocol access. Existing CDP scripts work unchanged.
- **MCP Client Support** — Claude Desktop, Cursor, Codex, OpenCode can use Browser Run as their remote browser.
- **WebMCP Support** — let websites expose MCP tools so agents call them by intent, not by selector.
- **Session Recordings** — `recording: true` on launch; replay with rrweb-player. Full DOM changes, user interactions, page navigation.
- **Higher limits** — 120 concurrent browsers (up from 30); 10 req/s for Quick Actions.
- **Free on both Workers Free and Workers Paid** plans.
- **Kitesurf (beta, August 2026)** — a stateless V8-isolate browser for agents. No Chromium underneath. 3.1–3.8× less CPU and 4.7–7.0× less memory than Chromium on common agent tasks. Chromium is ~1.7–1.8× faster on wall time; Kitesurf wins on cost per session. Passes 215,000+ Web Platform Tests.

### What the agent actually needs (and how Browser Run maps to it)

| Need | Browser Run support |
|---|---|
| Browsers on-demand | Chrome on Cloudflare's global network, on demand |
| A way to control the browser | Navigate, click, fill forms, screenshot via Puppeteer, Playwright, CDP (new), MCP client (new), WebMCP (new) |
| Observability | Live View (new), Session Recordings (new), Dashboard redesign (new) |
| Human intervention | Human in the Loop (new) |
| Scale | 10 req/s Quick Actions; 120 concurrent browsers (4×) |

## Patterns

### MCP client (Claude Desktop, Cursor, Codex, OpenCode) drives a remote browser

```json
// claude_desktop_config.json
{ "mcpServers": { "browser-run": { "url": "https://<your-browser-run-endpoint>/mcp" } } }
```

### Live View from code

```ts
const session = await env.BROWSER.launch({ recording: true });
const url = session.devtoolsFrontendURL; // open this in Chrome for Live View
```

### Session recording replay

```ts
const session = await env.BROWSER.launch({ recording: true });
// ... agent drives browser ...
await session.close();
// Recording is at: dashboard Runs tab, or fetch via API and replay with rrweb-player
```

### Kitesurf (agent-first, beta) — same API, different browser

```ts
const session = await env.BROWSER.launch({ browser: "kitesurf" });
// Same Puppeteer / Playwright / CDP / MCP API.
// 3.1–3.8× less CPU, 4.7–7.0× less memory than Chromium.
// Falls back to Chromium for: video, WebGL, TLS-fingerprint bot challenges, long authenticated stateful sessions.
```

### Human in the Loop handoff

```ts
const result = await env.BROWSER.run({
  goal: "Log in to the admin panel and reset the user's MFA",
  humanInLoop: true,                          // pause on login / edge case
  // handoff payload is shown in the dashboard
});
```

### WebMCP — agent calls website-exposed tools

```ts
// Site exposes MCP tools via navigator.modelContextTesting
const tools = await session.evaluate(() => navigator.modelContextTesting.listTools());
const result = await session.callTool("book_flight", { from: "SFO", to: "JFK" });
```

## Verification

- **Cold start p95** < 3 s for a new session, < 1 s for a warm one.
- **Concurrency** — verify the 120-browser limit on the Workers Paid plan; 30 on Free.
- **Live View latency** — the dashboard Live Sessions tab should update within ~1 s of agent action.
- **Recording size** — a 5-minute task should produce < 50 MB of rrweb data. If larger, check for noisy DOM mutations.
- **Kitesurf fallback** — try a WebGL or video page on `browser: "kitesurf"`; expect an explicit fallback to Chromium.
- **HITL handoff latency** — time from "agent needs human" to "human takes control" should be < 30 s in a normal ops flow.

## Gotchas

- **Kitesurf is in beta.** Strong for compatible sites and one-shot tasks; Chromium is the fallback for complex pages, video, WebGL, and long authenticated sessions.
- **WebMCP requires the site to opt in.** The site must expose `navigator.modelContextTesting.listTools()`. Most sites don't.
- **Session recordings are rrweb**, not raw video. Replay needs rrweb-player; downstream tooling (Puppeteer replay, video export) is not built in.
- **MCP client support is for the four named clients** (Claude Desktop, Cursor, Codex, OpenCode). For other MCP clients, use the CDP endpoint directly.
- **Browser Run is on Workers Free and Paid**; sandbox pricing for underlying containers is separate (see `cloudflare/sandbox-2026.md`).
- **CAPTCHA / TLS-fingerprint bot challenges** are still a problem on Kitesurf. For high-stealth workloads, consider Browser Use Cloud or stealth browser providers (Browser Use reports 81% success on the Stealth Benchmark vs 42% for Browserbase).
- **120 concurrent browsers** is the *concurrent* limit; total monthly sessions is metered separately.
- **Free plan concurrent limit is 30**, not 120.

## Related

- `documentation/categories/cloudflare/browser-run-best-practices.md` — pre-2026 patterns
- `documentation/categories/cloudflare/sandbox-2026.md` — for code-execution rather than browser-driving
- `documentation/categories/cloudflare/ai-search-2026.md` — retrieval layer often paired with browser agents
- `documentation/categories/patterns/agent-observability-2026.md` — OTel spans for browser actions
- `documentation/categories/lessons/human-in-the-loop.md` — the HITL handoff pattern
- `documentation/categories/security/ai-agent-security.md` — Rule of Two applies to browser creds and egress

## Source URLs (verified 2026-08-09)

- "Browser Run: give your agents a browser" (Cloudflare blog) — https://blog.cloudflare.com/browser-run-for-ai-agents/
- "Cloudflare Introduces Kitesurf: An Agent-First Web Browser" (marktechpost, 2026-08-06) — https://www.marktechpost.com/2026/08/06/cloudflare-introduces-kitesurf-an-agent-first-web-browser-that-runs-entirely-in-v8-isolates-on-cloudflare-workers/
- "The Agentic Browser Landscape in 2026: A Complete Guide" (nohacks) — https://nohacks.co/blog/agentic-browser-landscape-2026
- "State of Browser Use, May 2026" (michaellivs) — https://michaellivs.com/blog/state-of-browser-use-2026/
- "The Ultimate Guide to Web Scraping (2026)" (browser-use) — https://browser-use.com/posts/web-scraping-guide-2026
- WebVoyager leaderboard — referenced via michaellivs.com post
- Browser Use Stealth Benchmark — https://github.com/browser-use/benchmark
