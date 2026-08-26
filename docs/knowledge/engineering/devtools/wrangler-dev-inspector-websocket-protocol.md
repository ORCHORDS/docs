# Wrangler Dev Inspector WebSocket Protocol

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You need to programmatically attach a debugger, scrape runtime errors, or build
a custom DevTools integration against `wrangler dev`. The process exposes a
Chrome DevTools Protocol (CDP) WebSocket, but the port, path, and lifecycle
behaviour are undocumented and change between Wrangler versions.

---

## Context

`wrangler dev` starts Miniflare (or the remote runtime stub) and registers a
CDP-compatible inspector on `localhost:9229` by default (overridable via
`--inspector-port`). When the Worker reloads the WebSocket server restarts and
the session ID embedded in the path changes. Any external tooling must therefore
treat the connection as ephemeral and re-negotiate after each hot reload.

The same protocol is spoken by Chrome DevTools, VS Code's Node debugger
adapter, and any tool that speaks CDP/DAP over WebSocket. Wrangler also surfaces
a `/json` HTTP endpoint (port 9229) that returns the active targets list,
matching the format used by `chrome://inspect`.

---

## 1. Discovering the Active Inspector URL

```typescript
// scripts/discover-inspector.ts
import { setTimeout } from "node:timers/promises";

const INSPECTOR_PORT = process.env.INSPECTOR_PORT ?? "9229";

interface CdpTarget {
  id: string;
  title: string;
  type: string;
  webSocketDebuggerUrl: string;
  devtoolsFrontendUrl: string;
}

async function fetchTargets(retries = 10): Promise<CdpTarget[]> {
  for (let i = 0; i < retries; i++) {
    try {
      const res = await fetch(`http://localhost:${INSPECTOR_PORT}/json`);
      if (res.ok) return res.json() as Promise<CdpTarget[]>;
    } catch {
      // runtime not ready yet
    }
    await setTimeout(500);
  }
  throw new Error("Inspector did not become available within 5 s");
}

const targets = await fetchTargets();
const worker = targets.find((t) => t.type === "node"); // Wrangler labels it "node"
if (!worker) throw new Error("No worker target found");
console.log("WebSocket URL:", worker.webSocketDebuggerUrl);
```

---

## 2. Opening a Raw CDP Session

```typescript
// scripts/cdp-client.ts
import WebSocket from "ws"; // npm i -D ws @types/ws

type CdpMessage = { id: number; method: string; params?: unknown };
type CdpResult = { id: number; result?: unknown; error?: unknown };

export class CdpSession {
  private ws: WebSocket;
  private pending = new Map<number, (r: CdpResult) => void>();
  private seq = 1;

  constructor(wsUrl: string) {
    this.ws = new WebSocket(wsUrl);
    this.ws.on("message", (raw) => {
      const msg: CdpResult = JSON.parse(raw.toString());
      this.pending.get(msg.id)?.(msg);
      this.pending.delete(msg.id);
    });
  }

  ready(): Promise<void> {
    return new Promise((res, rej) => {
      this.ws.once("open", res);
      this.ws.once("error", rej);
    });
  }

  send<T>(method: string, params: unknown = {}): Promise<T> {
    return new Promise((resolve, reject) => {
      const id = this.seq++;
      const msg: CdpMessage = { id, method, params };
      this.pending.set(id, (r) =>
        r.error ? reject(r.error) : resolve(r.result as T)
      );
      this.ws.send(JSON.stringify(msg));
    });
  }

  close() {
    this.ws.close();
  }
}
```

---

## 3. Enabling the Runtime and Capturing Console Output

```typescript
// scripts/capture-console.ts
import { CdpSession } from "./cdp-client.js";

const session = new CdpSession(workerWsUrl);
await session.ready();

// Activate domains
await session.send("Runtime.enable");
await session.send("Debugger.enable");

// Listen for console API calls
session["ws"].on("message", (raw: Buffer) => {
  const event = JSON.parse(raw.toString());
  if (event.method === "Runtime.consoleAPICalled") {
    const args: Array<{ value?: unknown }> = event.params.args;
    console.log("[Worker]", args.map((a) => a.value).join(" "));
  }
  if (event.method === "Runtime.exceptionThrown") {
    const { exceptionDetails } = event.params;
    console.error("[Worker Error]", exceptionDetails.text);
  }
});

// Evaluate a snippet inside the worker runtime
const { result } = await session.send<{ result: { value: unknown } }>(
  "Runtime.evaluate",
  { expression: "typeof caches", returnByValue: true }
);
console.log("caches type:", result.value); // "object"
```

---

## 4. Setting Breakpoints via Source-Map-Resolved URLs

```typescript
// scripts/set-breakpoint.ts
import { CdpSession } from "./cdp-client.js";

await session.send("Debugger.enable");

// Wrangler emits scriptParsed events with the source URL from wrangler.toml
session["ws"].on("message", (raw: Buffer) => {
  const event = JSON.parse(raw.toString());
  if (event.method === "Debugger.scriptParsed") {
    const { scriptId, url } = event.params as { scriptId: string; url: string };
    if (url.endsWith("src/handler.ts")) {
      session.send("Debugger.setBreakpoint", {
        location: { scriptId, lineNumber: 14, columnNumber: 0 },
      });
    }
  }
});
```

---

## 5. Reconnecting After Hot Reload

```typescript
// scripts/resilient-inspector.ts
import { setTimeout } from "node:timers/promises";
import { CdpSession } from "./cdp-client.js";
import { fetchTargets } from "./discover-inspector.js";

async function attachLoop(signal: AbortSignal) {
  while (!signal.aborted) {
    const [target] = await fetchTargets();
    const session = new CdpSession(target.webSocketDebuggerUrl);

    await session.ready();
    await session.send("Runtime.enable");
    console.log("Attached to", target.webSocketDebuggerUrl);

    // Wait for disconnect (hot reload closes the socket)
    await new Promise<void>((res) =>
      session["ws"].once("close", res)
    );
    console.log("Session closed — reconnecting in 1 s");
    await setTimeout(1000);
    session.close();
  }
}

const ac = new AbortController();
process.on("SIGINT", () => ac.abort());
attachLoop(ac.signal);
```

---

## 6. Launching Wrangler with a Fixed Inspector Port

```toml
# wrangler.toml
[dev]
inspector_port = 9229
```

```bash
# Or via CLI flag:
wrangler dev --inspector-port 9229
```

```typescript
// package.json script shorthand
{
  "scripts": {
    "dev": "wrangler dev --inspector-port 9229",
    "debug": "wrangler dev --inspector-port 9229 & node --import tsx/esm scripts/capture-console.ts"
  }
}
```

---

## Anti-patterns

- **Hardcoding the session path** – The path (`/ws/…` suffix) is regenerated on
  every reload. Always fetch `/json` first to get the live URL.
- **Connecting before the runtime is ready** – Wrangler may start the HTTP
  server before the worker JS is compiled. Retry `/json` with back-off (section 1).
- **Forgetting `Runtime.enable`** – Console and exception events are not emitted
  until you activate the domain explicitly.
- **Bundling `ws` into the Worker** – The WebSocket client used above is a
  `devDependency` in the scripts folder; never import it inside the Worker
  source tree.

---

## Gotchas

- The inspector port is separate from the wrangler dev HTTP port (default 8787).
  Firewalls and Docker port mappings must expose both.
- `wrangler dev --remote` still opens a local inspector proxy; breakpoints set
  inside that session reflect the local bundle, not the production source.
- Wrangler labels the CDP target `type: "node"` even though the runtime is V8
  Workers. Filter by `title` if multiple targets are listed.
- Chrome DevTools will also connect to port 9229 if you visit
  `chrome://inspect`. If both a custom script and Chrome attach simultaneously,
  some CDP commands return errors because only one debugger can pause execution.

---

## Verification

```bash
# 1. Start wrangler dev
wrangler dev --inspector-port 9229 &

# 2. Confirm /json endpoint responds
curl -s http://localhost:9229/json | jq '.[0].webSocketDebuggerUrl'

# 3. Quick one-liner evaluation
node -e "
  const ws = new (require('ws'))(process.argv[1]);
  ws.on('open', () => ws.send(JSON.stringify({id:1,method:'Runtime.evaluate',params:{expression:'1+1',returnByValue:true}})));
  ws.on('message', d => { console.log(d.toString()); ws.close(); });
" $(curl -s http://localhost:9229/json | node -e "process.stdin.resume();let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>console.log(JSON.parse(d)[0].webSocketDebuggerUrl))")
```

---

## Related

- `workers-devtools-protocol-chrome-debugger.md`
- `wrangler-dev-local-vs-remote-mode-decision-tree.md`
- `wrangler-unstable-dev-programmatic-api-testing.md`
- `miniflare-durable-objects-fake-clock-testing.md`

---

## Sources

- Chromium DevTools Protocol specification: https://chromedevtools.github.io/devtools-protocol/
- Wrangler source — `packages/wrangler/src/inspect.ts` (Cloudflare/workers-sdk)
- Miniflare inspector proxy: https://github.com/cloudflare/miniflare
- VS Code Node.js debugger protocol docs: https://code.visualstudio.com/docs/nodejs/nodejs-debugging
