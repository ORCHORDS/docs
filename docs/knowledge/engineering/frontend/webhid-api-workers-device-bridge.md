# WebHID API + Cloudflare Workers Device Bridge

Date: 2026-08-23 / Author: example.com / Status: production

---

**Symptom / Use-case:** You need a web app to communicate with USB HID devices (game controllers, MIDI controllers, drawing tablets, barcode scanners, custom hardware) and relay device data or firmware updates through a Cloudflare Workers backend without a native app.

**Context:** The WebHID API (`navigator.hid`) lets Chromium-based browsers open raw HID report channels to allowed devices. Workers act as the relay layer: storing device sessions in D1, caching device descriptors in KV, and streaming report data through Durable Objects WebSocket connections to multi-tab or multi-client observers.

---

## Feature Detection

```typescript
// lib/hid.ts
export function isWebHIDSupported(): boolean {
  return 'hid' in navigator;
}

export async function requestDevice(
  filters: HIDDeviceFilter[]
): Promise<HIDDevice> {
  if (!isWebHIDSupported()) {
    throw new DOMException('WebHID not supported', 'NotSupportedError');
  }
  const [device] = await navigator.hid.requestDevice({ filters });
  if (!device) throw new Error('No device selected');
  return device;
}
```

## Opening a Device and Reading Reports

```typescript
// lib/hid-session.ts
export class HIDSession {
  private device: HIDDevice;
  private abortController = new AbortController();

  constructor(device: HIDDevice) {
    this.device = device;
  }

  async open(): Promise<void> {
    if (!this.device.opened) await this.device.open();

    this.device.addEventListener(
      'inputreport',
      (event: HIDInputReportEvent) => {
        this.onReport(event.reportId, new Uint8Array(event.data.buffer));
      },
      { signal: this.abortController.signal }
    );
  }

  private onReport(reportId: number, data: Uint8Array): void {
    // Forward to Workers relay
    sendReportToWorker({
      productId: this.device.productId,
      vendorId: this.device.vendorId,
      reportId,
      data: Array.from(data),
    });
  }

  async close(): Promise<void> {
    this.abortController.abort();
    await this.device.close();
  }
}

async function sendReportToWorker(payload: unknown): Promise<void> {
  // Fire-and-forget; use WebSocket for low-latency streaming
  await fetch('/api/hid/report', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}
```

## Cloudflare Worker — Store Report + Forward to Durable Object

```typescript
// workers/hid-bridge.ts
import { Env } from './bindings';

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    if (url.pathname === '/api/hid/report' && req.method === 'POST') {
      const body = await req.json<{
        vendorId: number; productId: number;
        reportId: number; data: number[];
      }>();

      // Persist latest report to KV for polling clients
      const cacheKey = `hid:${body.vendorId}:${body.productId}:latest`;
      await env.KV.put(cacheKey, JSON.stringify(body), { expirationTtl: 300 });

      // Forward to Durable Object for real-time broadcast
      const id = env.HID_RELAY.idFromName(`${body.vendorId}-${body.productId}`);
      const stub = env.HID_RELAY.get(id);
      await stub.fetch(new Request('https://internal/broadcast', {
        method: 'POST',
        body: JSON.stringify(body),
      }));

      return new Response(null, { status: 204 });
    }

    if (url.pathname === '/api/hid/ws') {
      const vendorId = url.searchParams.get('vendor') ?? '0';
      const productId = url.searchParams.get('product') ?? '0';
      const id = env.HID_RELAY.idFromName(`${vendorId}-${productId}`);
      const stub = env.HID_RELAY.get(id);
      return stub.fetch(req);
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

## Durable Object — WebSocket Relay

```typescript
// workers/hid-relay-do.ts
export class HIDRelay implements DurableObject {
  private sessions = new Set<WebSocket>();

  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);

    if (url.pathname === '/broadcast') {
      const payload = await req.text();
      for (const ws of this.sessions) {
        if (ws.readyState === WebSocket.OPEN) ws.send(payload);
      }
      return new Response(null, { status: 204 });
    }

    // WebSocket upgrade from browser
    const upgradeHeader = req.headers.get('Upgrade');
    if (upgradeHeader !== 'websocket') {
      return new Response('Expected WebSocket', { status: 426 });
    }
    const { 0: client, 1: server } = new WebSocketPair();
    server.accept();
    this.sessions.add(server);
    server.addEventListener('close', () => this.sessions.delete(server));
    return new Response(null, { status: 101, webSocket: client });
  }
}
```

## Browser-Side WebSocket Consumer

```typescript
// lib/hid-observer.ts
export function observeDevice(
  vendorId: number,
  productId: number,
  onReport: (data: number[]) => void
): () => void {
  const ws = new WebSocket(
    `wss://api.example.com/api/hid/ws?vendor=${vendorId}&product=${productId}`
  );

  ws.onmessage = (event) => {
    const { data } = JSON.parse(event.data as string) as { data: number[] };
    onReport(data);
  };

  return () => ws.close();
}
```

## Sending Output Reports (Write to Device)

```typescript
// lib/hid-output.ts
export async function sendOutputReport(
  device: HIDDevice,
  reportId: number,
  payload: Uint8Array
): Promise<void> {
  if (!device.opened) await device.open();
  await device.sendReport(reportId, payload);
}

// Example: set LED on a custom device
await sendOutputReport(device, 0x02, new Uint8Array([0x01, 0xFF, 0x00, 0x00]));
```

## Anti-patterns

- **Polling the HID device in a `setInterval`** — the API is event-driven via `inputreport`; polling wastes CPU and blocks the event loop.
- **Not calling `device.close()` on unmount** — open HID connections block the device from use by other tabs or apps.
- **Storing raw binary reports in D1 as blobs** — JSON-encode the `Uint8Array` as a plain number array or base64 for D1 TEXT column compatibility.
- **Calling `requestDevice()` outside a user gesture** — the browser requires a transient activation (click, keypress).

## Gotchas

- WebHID is **Chromium-only** (Chrome, Edge, Opera); Safari and Firefox do not support it as of 2026.
- The API is only available in **secure contexts** (`https://` or `localhost`).
- Devices must match an **allow-list filter** (`vendorId` / `productId`) — wildcard `filters: []` is blocked in most embeddings.
- Durable Objects WebSocket connections count against the **DO active-connection** limit; implement heartbeat pings every 30 s.
- `wrangler.toml` must declare the DO binding and migration: `[[durable_objects.bindings]]` + `[[migrations]]`.

## Verification

```bash
# Local dev with Durable Objects
wrangler dev --local --persist-to .wrangler/state

# Test report relay
curl -X POST http://localhost:8787/api/hid/report \
  -H 'Content-Type: application/json' \
  -d '{"vendorId":1234,"productId":5678,"reportId":1,"data":[0,255,128]}'
# Expect: 204

# Confirm KV cache entry
wrangler kv key get "hid:1234:5678:latest" --binding KV --local
```

## Related

- `web-serial-api-workers-device-bridge.md`
- `web-bluetooth-api-workers-device-bridge.md`
- `web-usb-api` (not yet documented)
- `websocket-durable-objects-realtime-ui.md`
- `webrtc-signaling-durable-objects-edge.md`

## Sources

- MDN WebHID API: https://developer.mozilla.org/en-US/docs/Web/API/WebHID_API
- WebHID Explainer: https://github.com/WICG/webhid/blob/main/EXPLAINER.md
- Cloudflare Durable Objects: https://developers.cloudflare.com/durable-objects/
- Cloudflare KV: https://developers.cloudflare.com/kv/
