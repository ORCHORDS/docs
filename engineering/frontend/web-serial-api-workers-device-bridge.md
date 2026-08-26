# Web Serial API: Browser-to-Device Bridge with Cloudflare Workers Relay

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
You are building a web-based tool for configuring or reading data from USB serial devices (microcontrollers, barcode scanners, label printers, industrial sensors) and need to bridge device output to a Cloudflare Workers backend for logging, remote monitoring, or triggering server-side workflows. The browser's Web Serial API provides direct USB/serial access, but the data must flow to the cloud.

## Context
The Web Serial API (`navigator.serial`) is available in Chrome/Edge 89+ (including Electron apps) on HTTPS origins and `localhost`. It requires a transient user activation (a button click) to call `requestPort()` the first time, after which the port can be reopened by origin via `getPorts()`. Data flows as `ReadableStream`/`WritableStream`, making it composable with the Streams API. Cloudflare Workers receive the forwarded data via HTTP POST or WebSocket. The pattern is common in IoT dashboards, point-of-sale systems, lab equipment, and maker tools.

## Requesting and Opening a Serial Port

```typescript
// lib/serial.ts

export interface SerialConfig {
  baudRate: number;
  dataBits?: 7 | 8;
  stopBits?: 1 | 2;
  parity?: "none" | "even" | "odd";
  flowControl?: "none" | "hardware";
}

export class SerialDevice {
  private port: SerialPort | null = null;
  private reader: ReadableStreamDefaultReader<string> | null = null;
  private abortController = new AbortController();

  async requestPort(filters: SerialPortFilter[] = []): Promise<void> {
    if (!("serial" in navigator)) {
      throw new Error("Web Serial API is not supported in this browser.");
    }
    this.port = await navigator.serial.requestPort({ filters });
  }

  async open(config: SerialConfig): Promise<void> {
    if (!this.port) throw new Error("No port selected. Call requestPort() first.");
    await this.port.open(config);
  }

  async reconnectSaved(config: SerialConfig): Promise<boolean> {
    const ports = await navigator.serial.getPorts();
    if (ports.length === 0) return false;
    this.port = ports[0];
    await this.port.open(config);
    return true;
  }

  async *lines(): AsyncGenerator<string> {
    if (!this.port?.readable) throw new Error("Port is not open.");

    const decoder = new TextDecoderStream();
    const pipePromise = this.port.readable.pipeTo(decoder.writable, {
      signal: this.abortController.signal,
    }).catch(() => {/* closed or aborted */});

    // Split on newlines
    let buffer = "";
    this.reader = decoder.readable.getReader();

    try {
      while (true) {
        const { value, done } = await this.reader.read();
        if (done) break;
        buffer += value;
        const lines = buffer.split(/\r?\n/);
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (line.trim()) yield line;
        }
      }
    } finally {
      this.reader.releaseLock();
      await pipePromise;
    }
  }

  async write(data: string): Promise<void> {
    if (!this.port?.writable) throw new Error("Port is not writable.");
    const encoder = new TextEncoderStream();
    const pipe = encoder.readable.pipeTo(this.port.writable, {
      preventClose: true,
    });
    const writer = encoder.writable.getWriter();
    await writer.write(data);
    writer.releaseLock();
    await pipe;
  }

  async close(): Promise<void> {
    this.abortController.abort();
    this.reader?.cancel();
    await this.port?.close();
    this.port = null;
    this.abortController = new AbortController();
  }
}
```

## Forwarding Serial Data to Cloudflare Workers

```typescript
// lib/serial-relay.ts
import { SerialDevice } from "./serial";

interface RelayConfig {
  workerUrl: string;
  deviceId: string;
  batchIntervalMs?: number;
  maxBatchSize?: number;
}

export class SerialWorkerRelay {
  private device: SerialDevice;
  private config: Required<RelayConfig>;
  private batch: string[] = [];
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor(device: SerialDevice, config: RelayConfig) {
    this.device = device;
    this.config = {
      batchIntervalMs: 2000,
      maxBatchSize: 50,
      ...config,
    };
  }

  private async flush(): Promise<void> {
    if (this.batch.length === 0) return;
    const toSend = this.batch.splice(0);
    try {
      await fetch(this.config.workerUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Device-Id": this.config.deviceId,
        },
        body: JSON.stringify({
          deviceId: this.config.deviceId,
          timestamp: new Date().toISOString(),
          lines: toSend,
        }),
        // Use keepalive so the request survives page navigation
        keepalive: true,
      });
    } catch (err) {
      console.error("[SerialRelay] Flush failed:", err);
      // Re-queue on failure
      this.batch.unshift(...toSend);
    }
  }

  async start(): Promise<void> {
    this.timer = setInterval(() => this.flush(), this.config.batchIntervalMs);

    for await (const line of this.device.lines()) {
      this.batch.push(line);
      if (this.batch.length >= this.config.maxBatchSize) {
        await this.flush();
      }
    }

    // Final flush when the device disconnects
    await this.flush();
    if (this.timer) clearInterval(this.timer);
  }

  async stop(): Promise<void> {
    if (this.timer) clearInterval(this.timer);
    await this.flush();
    await this.device.close();
  }
}
```

## Workers Handler: Receiving and Storing Device Data

```typescript
// workers/serial-ingest.ts
import { Env } from "./types";

interface DeviceBatch {
  deviceId: string;
  timestamp: string;
  lines: string[];
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    let batch: DeviceBatch;
    try {
      batch = await request.json<DeviceBatch>();
    } catch {
      return new Response(JSON.stringify({ error: "Invalid JSON" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (!batch.deviceId || !Array.isArray(batch.lines)) {
      return new Response(JSON.stringify({ error: "Missing deviceId or lines" }), {
        status: 422,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Insert each line as a row in D1
    const stmt = env.DB.prepare(
      "INSERT INTO device_logs (device_id, received_at, line) VALUES (?, ?, ?)"
    );
    const stmts = batch.lines.map((line) =>
      stmt.bind(batch.deviceId, batch.timestamp, line.slice(0, 1024))
    );

    try {
      await env.DB.batch(stmts);
    } catch (err) {
      console.error("D1 batch insert failed:", err);
      return new Response(JSON.stringify({ error: "Storage error" }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Fan out to Durable Object for live dashboard via WebSocket
    const id = env.DEVICE_DO.idFromName(batch.deviceId);
    const stub = env.DEVICE_DO.get(id);
    await stub.fetch(
      new Request("https://internal/broadcast", {
        method: "POST",
        body: JSON.stringify({ lines: batch.lines }),
        headers: { "Content-Type": "application/json" },
      })
    );

    return new Response(JSON.stringify({ accepted: batch.lines.length }), {
      status: 202,
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

## React Hook: Serial Device State Management

```tsx
// hooks/useSerialDevice.ts
import { useState, useCallback, useRef, useEffect } from "react";
import { SerialDevice, SerialConfig } from "@/lib/serial";
import { SerialWorkerRelay } from "@/lib/serial-relay";

type ConnectionStatus = "disconnected" | "connecting" | "connected" | "error";

export function useSerialDevice(
  workerUrl: string,
  config: SerialConfig,
  deviceIdPrefix = "dev"
) {
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const [lines, setLines] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const deviceRef = useRef<SerialDevice | null>(null);
  const relayRef = useRef<SerialWorkerRelay | null>(null);

  const connect = useCallback(async () => {
    setStatus("connecting");
    setError(null);
    try {
      const device = new SerialDevice();
      await device.requestPort();
      await device.open(config);
      deviceRef.current = device;

      const deviceId = `${deviceIdPrefix}-${Date.now()}`;
      const relay = new SerialWorkerRelay(device, { workerUrl, deviceId });
      relayRef.current = relay;

      // Stream lines to local state for live display
      setStatus("connected");
      (async () => {
        for await (const line of device.lines()) {
          setLines((prev) => [...prev.slice(-199), line]);
        }
        setStatus("disconnected");
      })();

      relay.start(); // Non-blocking; flushes to Workers in background
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [workerUrl, config, deviceIdPrefix]);

  const disconnect = useCallback(async () => {
    await relayRef.current?.stop();
    deviceRef.current = null;
    relayRef.current = null;
    setStatus("disconnected");
  }, []);

  useEffect(() => () => { relayRef.current?.stop(); }, []);

  return { status, lines, error, connect, disconnect };
}
```

## Anti-patterns

- **Auto-requesting the port on page load** — `navigator.serial.requestPort()` requires a user gesture and will throw `DOMException: Must be handling a user gesture` if called outside a click/key handler.
- **Not releasing the `reader` lock before calling `port.close()`** — If the reader is still locked, `port.close()` will throw. Always call `reader.cancel()` and wait for the generator to exit before closing.
- **Sending every line as a separate HTTP POST** — At 9600 baud a device can emit hundreds of lines per second. Batch data with a flush interval (2–5 seconds) to avoid overwhelming Workers rate limits and incurring excess request costs.
- **Hardcoding baud rate** — Different devices use different baud rates (9600, 115200, etc.). Surface this as a configurable UI dropdown rather than a constant.
- **Not setting `keepalive: true` on the flush fetch** — Without `keepalive`, in-flight requests are cancelled when the user navigates away, losing buffered data.

## Gotchas

- **Web Serial is Chrome/Edge only** — Firefox and Safari have not shipped it. Always render a browser compatibility notice and consider an Electron/Tauri wrapper for cross-platform deployments.
- **`getPorts()` returns previously granted ports without a user gesture** — Use this on page load to reconnect automatically, but still require a button click for first-time pairing.
- **Device disconnect events** — When the USB cable is unplugged, `readable` closes and `lines()` exits the loop. Listen for the `navigator.serial.ondisconnect` event to update UI state independently of the stream loop.
- **Workers CPU limit on high-volume inserts** — A D1 `batch()` call with 50 inserts costs minimal CPU, but if lines arrive faster than flush cycles, the batch can grow very large. Cap batch size and implement backpressure.
- **CORS on the Workers endpoint** — The browser sends a preflight OPTIONS request before the POST. Handle `OPTIONS` and return `Access-Control-Allow-*` headers, or use a same-origin Pages Function to avoid CORS entirely.

## Verification

1. Connect an Arduino Uno configured to print `"PING\n"` every second at 9600 baud; confirm lines appear in the React `lines` state array.
2. Check the D1 table after 10 seconds: `SELECT COUNT(*) FROM device_logs WHERE device_id = ?`; confirm approximately 10 rows.
3. Unplug the USB cable and verify `status` transitions to `"disconnected"` within 2 seconds.
4. Call `connect()` from a `setTimeout` (simulating a non-gesture call) and confirm it throws with a user gesture error.
5. Navigate away from the page during active streaming and confirm the pending batch is flushed (check D1 row count matches expected lines).

## Related

- `websocket-durable-objects-realtime-ui.md` — live dashboard via WebSocket to the Durable Object
- `indexeddb-offline-sync-cloudflare-d1-workers.md` — D1 batch insert patterns
- `streaming-html-workers-react-rendertopipeablestream.md` — streaming patterns in Workers
- `compression-streams-api-workers-client.md` — compressing bulk device data before upload

## Sources

- https://developer.mozilla.org/en-US/docs/Web/API/Web_Serial_API
- https://web.dev/serial/
- https://developers.cloudflare.com/d1/platform/client-api/
