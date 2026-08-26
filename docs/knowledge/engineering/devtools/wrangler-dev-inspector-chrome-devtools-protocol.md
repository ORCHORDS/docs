# Using Chrome DevTools Protocol (CDP) with `wrangler dev`

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to step through a Cloudflare Worker with real breakpoints, inspect KV and D1 network calls, or profile CPU usage — rather than relying on `console.log` and guessing.

## Context

`wrangler dev` ships a built-in V8 inspector that speaks the Chrome DevTools Protocol (CDP). When you pass `--inspect` the runtime publishes a WebSocket endpoint you can attach any CDP-capable debugger to — including Chrome DevTools, VS Code's built-in debugger, and WebStorm. The feature works in both `--local` (Miniflare V8 isolate) and `--remote` (edge preview) modes, though the underlying mechanism differs.

## Starting the Inspector Endpoint

```bash
# Local mode — full V8 inspector, breakpoints + memory profiling
npx wrangler dev src/index.ts --local --inspect
# Output:
#   Debugger listening on ws://127.0.0.1:9229/…
#   For help, see: https://nodejs.org/en/docs/inspector

# Remote mode — attaches a Tail Worker; only console/exception sampling
npx wrangler dev src/index.ts --remote --inspect

# Pin the inspector port (useful in CI or Docker)
npx wrangler dev src/index.ts --local --inspect --inspector-port 9230
```

Open `chrome://inspect` in Chrome, click **Configure…**, add `localhost:9229`, then click **inspect** under the Worker target that appears.

## Connecting Chrome DevTools and Setting Breakpoints

```typescript
// src/index.ts  — the Worker under debug
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Set a breakpoint on the next line in DevTools Sources panel
    const url = new URL(request.url);

    if (url.pathname === '/kv-read') {
      // Breakpoint here lets you inspect `env.MY_KV` in the Scope panel
      const value = await env.MY_KV.get('config');
      return new Response(value ?? 'not found');
    }

    if (url.pathname === '/d1-query') {
      const result = await env.DB.prepare(
        'SELECT * FROM users WHERE id = ?'
      ).bind(url.searchParams.get('id')).first();
      return Response.json(result);
    }

    return new Response('ok');
  },
};
```

Source maps are resolved automatically when `wrangler dev` detects a `tsconfig.json`. In the DevTools **Sources** panel you will see the original `.ts` files, not the compiled output.

## Inspecting KV and D1 Calls in the Network Panel

Local Miniflare emulates KV and D1 over HTTP internally. In `--local --inspect` mode those internal fetches appear in the **Network** panel under the `Fetch/XHR` filter with URLs like `http://localhost:8787/__mf__/kv/MY_KV/config`. You can inspect request headers, response payloads, and timing — useful for spotting missing `cacheTtl` options or unintentional list-without-limit calls.

```bash
# Trigger a request from a second terminal while the debugger is paused
curl http://localhost:8787/kv-read
```

The Worker execution pauses at your breakpoint; the Network panel shows the pending KV fetch queued behind the paused JS stack frame.

## VS Code Launch Configuration

```jsonc
// .vscode/launch.json
{
  "version": "0.2.0",
  "configurations": [
    {
      "type": "node",
      "request": "attach",
      "name": "Attach to wrangler dev",
      "port": 9229,
      "sourceMaps": true,
      // Remap compiled output back to TypeScript sources
      "sourceMapPathOverrides": {
        "webpack:///./*": "${workspaceFolder}/*"
      },
      "skipFiles": ["<node_internals>/**", "**/node_modules/**"]
    }
  ]
}
```

Start `wrangler dev --local --inspect`, then launch the **Attach to wrangler dev** configuration. Breakpoints set in `.ts` files resolve immediately.

## `--local` vs `--remote` Debugging Difference

| Aspect | `--local` | `--remote` |
|---|---|---|
| Mechanism | V8 inspector (CDP full) | Tail Worker log sampling |
| Breakpoints | Yes | No |
| Memory profiler | Yes | No |
| Real edge KV/D1 | No (Miniflare) | Yes |
| Console output | DevTools console | Streamed via `wrangler tail` |
| Latency | Instant reload | ~2 s publish round-trip |

Use `--local` for logic debugging; switch to `--remote` only when you need to verify behavior against live bindings.

## Anti-patterns

- **Leaving `--inspect` on in production CI** — the inspector port stays open and will block the process exit if nothing connects and `--inspect-brk` is accidentally used.
- **Relying on `debugger` statements in committed code** — Wrangler strips them in production builds but they are noise in code review.
- **Expecting full CDP in `--remote` mode** — remote mode does not support pausing execution; it only tails logs.

## Gotchas

- Chrome allows only one DevTools session per CDP target at a time. If you already have a tab open from a previous session, the new one will silently fail to connect.
- Source maps require `"sourceMap": true` in `tsconfig.json` and a `wrangler.toml` that does **not** set `minify = true`.
- On macOS, `chrome://inspect` sometimes caches stale targets. Use **Devices → Discover network targets → Configure** and remove/re-add `localhost:9229`.
- `--inspector-port 0` lets the OS pick a free port; `wrangler` prints the actual port to stderr.

## Verification

```bash
# Confirm the WebSocket endpoint is live
curl -s http://localhost:9229/json | jq '.[0].webSocketDebuggerUrl'
# Expected output:
# "ws://localhost:9229/…"

# Smoke-test a breakpoint non-interactively with node --inspect-brk and a CDP script
node -e "
  const CDP = require('chrome-remote-interface');
  CDP(async (client) => {
    const { Debugger } = client;
    await Debugger.enable();
    console.log('CDP connected');
    await client.close();
  });
"
```

## Related

- `miniflare-custom-storage-backend-testing.md`
- `vitest-coverage-thresholds-ci-enforcement-workers.md`
- [Wrangler CLI reference — `wrangler dev`](https://developers.cloudflare.com/workers/wrangler/commands/#dev)

## Sources

- Cloudflare Workers Docs: Debugging with DevTools — https://developers.cloudflare.com/workers/observability/dev-tools/
- Chrome DevTools Protocol — https://chromedevtools.github.io/devtools-protocol/
- Miniflare source: inspector implementation — https://github.com/cloudflare/workers-sdk
