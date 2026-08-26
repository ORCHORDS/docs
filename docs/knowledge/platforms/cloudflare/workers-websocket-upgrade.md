# workers-websocket-upgrade

**Issue:** Handling WebSocket upgrades inside a Cloudflare Worker
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Workers can act as WebSocket servers using the WebSocket API. The upgrade must be handled in the `fetch` handler; the Worker pairs a client socket with a server socket via `new WebSocketPair()`.

## Pattern / Solution

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const upgrade = request.headers.get('Upgrade');
    if (upgrade !== 'websocket') {
      return new Response('Expected WebSocket', { status: 426 });
    }

    const [client, server] = Object.values(new WebSocketPair());

    // Accept the server-side socket
    server.accept();

    server.addEventListener('message', (event) => {
      const msg = event.data as string;
      console.log('received:', msg);
      server.send(JSON.stringify({ echo: msg, ts: Date.now() }));
    });

    server.addEventListener('close', (event) => {
      console.log('closed', event.code, event.reason);
    });

    server.addEventListener('error', (event) => {
      console.error('ws error', event);
    });

    // Return 101 Switching Protocols with the client socket
    return new Response(null, {
      status: 101,
      webSocket: client,
    });
  },
};

// Proxying WebSocket to an upstream
async function proxyWebSocket(request: Request): Promise<Response> {
  const upstreamUrl = new URL(request.url);
  upstreamUrl.host = 'upstream.example.com';
  upstreamUrl.protocol = 'https:'; // Cloudflare handles ws:// → https:// internally

  const upstreamResponse = await fetch(upstreamUrl.toString(), {
    headers: request.headers,
    cf: { resolveOverride: 'upstream.example.com' },
  });

  // If upstream accepted the WebSocket, forward it
  if (upstreamResponse.webSocket) {
    const [client, server] = Object.values(new WebSocketPair());
    server.accept();
    upstreamResponse.webSocket.accept();

    server.addEventListener('message', e => upstreamResponse.webSocket!.send(e.data));
    upstreamResponse.webSocket.addEventListener('message', e => server.send(e.data));

    return new Response(null, { status: 101, webSocket: client });
  }

  return upstreamResponse;
}
```

## Gotchas
- `server.accept()` **must** be called before sending or receiving messages; forgetting it causes a silent hang.
- The response must have `status: 101` and a `webSocket` property — a plain `200` will not work.
- Workers using WebSockets count as a long-lived connection; the isolate stays alive until the socket closes.
- For stateful WebSocket sessions (reconnect, broadcast) use a **Durable Object** as the WebSocket server — see `durable-objects-websocket-hibernation.md`.
- `new WebSocketPair()` returns `{0: client, 1: server}`; use `Object.values()` to destructure reliably.
- Binary frames (`ArrayBuffer`) are supported; set `server.binaryType = 'arraybuffer'`.

## Related
- `durable-objects-websocket-hibernation.md`
- `workers-streaming-responses.md`
- `durable-objects-patterns.md`
