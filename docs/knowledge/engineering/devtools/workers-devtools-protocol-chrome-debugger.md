# Workers DevTools Protocol Chrome Debugger

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Setting `console.log` breakpoints across example project's feed ranking logic or DM encryption routines isn't enough — you need to step through the code, inspect closures, and watch variables mutate in real time. Wrangler's `--inspect` flag exposes a Chrome DevTools Protocol endpoint but the connection steps and limitations are easy to miss.

## Context

Cloudflare's local Workers runtime (`workerd`) implements the V8 Inspector Protocol, the same protocol Chrome DevTools uses. When `wrangler dev --inspect` is active, a WebSocket endpoint is opened at `localhost:9229` that any CDP-compatible client can attach to: Chrome DevTools, VS Code's built-in debugger, or standalone tools like `node-inspect`. This is distinct from the remote debugging preview available in the Cloudflare dashboard, which has a read-only log view only.

## Launching Wrangler in Inspect Mode

```bash
# Enable the inspector; default port is 9229
wrangler dev --local --inspect

# Override port if 9229 is occupied
wrangler dev --local --inspect-port 9230

# Combine with persistence so D1/R2/KV state survives restarts
wrangler dev --local --inspect --persist
```

Wrangler prints a line like:

```
Debugger listening on ws://127.0.0.1:9229/...
```

Copy that WebSocket URL — you need it for VS Code.

## Attaching Chrome DevTools

1. Open a new Chrome tab and navigate to `chrome://inspect`.
2. Under **Devices**, click **Configure…** and add `localhost:9229`.
3. The Worker target appears under **Remote Target**. Click **inspect**.
4. The Sources panel shows your Worker's compiled bundle. If source maps are configured, it resolves to TypeScript source files.

To get TypeScript source navigation, add to `wrangler.toml`:

```toml
[build]
command = "npm run build"

[dev]
source_maps = true
```

And ensure your `tsconfig.json` emits source maps:

```json
{
  "compilerOptions": {
    "sourceMap": true,
    "inlineSources": true
  }
}
```

## VS Code Launch Configuration

Add this to `.vscode/launch.json` for one-click attach without opening Chrome:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Attach to Wrangler Dev",
      "type": "node",
      "request": "attach",
      "port": 9229,
      "address": "localhost",
      "localRoot": "${workspaceFolder}",
      "remoteRoot": "/",
      "sourceMaps": true,
      "sourceMapPathOverrides": {
        "webpack:///*": "${workspaceFolder}/*"
      },
      "skipFiles": ["<node_internals>/**"],
      "resolveSourceMapLocations": [
        "${workspaceFolder}/**",
        "!**/node_modules/**"
      ]
    }
  ]
}
```

Start `wrangler dev --local --inspect` first, then press **F5** in VS Code to attach. Breakpoints set in `.ts` files resolve correctly if source maps are present.

## Conditional Breakpoints and Log Points

Inside Chrome DevTools or VS Code, you can set conditional breakpoints without touching source code:

- **Conditional breakpoint** (Chrome): right-click the gutter → **Add conditional breakpoint** → enter `userId === "usr_42"` to pause only for a specific user.
- **Log point** (Chrome): right-click → **Add log point** → `"feed length:", posts.length` — emits to the DevTools console without modifying code.
- **Tracepoint** (VS Code): same as log point, available in the Breakpoints panel.

These techniques are invaluable for debugging example project's anonymous feed without mutating production-like fixtures.

```typescript
// Example: feed ranking function you want to step through
export function rankPosts(posts: Post[], signals: SignalMap): Post[] {
  return posts
    .map((post) => ({
      post,
      score: computeScore(post, signals), // set breakpoint here
    }))
    .sort((a, b) => b.score - a.score)
    .map(({ post }) => post);
}
```

## Anti-patterns

- Running `wrangler dev --remote --inspect` — remote mode does NOT expose a local CDP endpoint; the inspector only works in `--local` mode
- Opening multiple `wrangler dev` processes on the same port; the second process will fail to bind `9229` silently
- Setting breakpoints before the devtools client is attached — they silently do not register; always attach first, then trigger the request
- Relying on the inspector for production debugging — use `wrangler tail` + Logpush instead

## Gotchas

- The WebSocket URL printed by Wrangler changes on each restart; you must re-attach after every `wrangler dev` reload
- VS Code's Node.js debugger loses the connection on hot-reload; configure `"restart": true` in `launch.json` to auto-reconnect
- `crypto.subtle` calls inside the Worker are synchronous from the debugger's perspective but may time out if you pause too long inside an async function
- Durable Object stubs pause the DO's event loop when you hit a breakpoint inside the DO — other requests to the same DO stall until you resume
- The `workerd` V8 version may differ from the production runtime version; edge-case V8 behaviour visible in the debugger might not reproduce in prod

## Verification

```bash
# Terminal 1 – start local dev with inspector
wrangler dev --local --inspect --persist

# Terminal 2 – send a request to trigger execution
curl -v http://localhost:8787/api/feed

# In Chrome:
# 1. chrome://inspect → Configure → localhost:9229
# 2. Click inspect on the Worker target
# 3. Open Sources panel — confirm .ts files are visible (not .js) when source maps are on
# 4. Set a breakpoint in rankPosts(), re-send curl, verify pause at breakpoint
```

## Related

- `vscode-launch-json-debugging.md`
- `vscode-debugging-config.md`
- `wrangler-dev-local-d1-r2-kv.md`
- `workers-sourcemaps-sentry-error-tracking.md` (if added)
- `chrome-devtools-2026.md`

## Sources

- https://developers.cloudflare.com/workers/testing/local-development/#inspector
- https://developers.cloudflare.com/workers/wrangler/commands/#dev
- https://chromedevtools.github.io/devtools-protocol/
- https://code.visualstudio.com/docs/nodejs/nodejs-debugging#_attaching-to-nodejs
