# Web MIDI API Workers Audio Pipeline

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A music production app or live performance tool hosted on Cloudflare Pages needs to receive MIDI events from connected hardware (keyboards, drum pads, controllers) and route those events through a Cloudflare Worker for logging, mapping, or triggering server-side actions (session recording, DAW automation via WebSocket, pattern storage in D1).

---

## Context

The Web MIDI API (`navigator.requestMIDIAccess()`) is available in Chrome 43+, Edge 79+, and Opera on desktop. It is not available in Firefox (without a flag) or Safari. It requires HTTPS and a user gesture for the first call, which triggers a browser permission prompt.

MIDI messages are binary: a three-byte `Uint8Array` [status, data1, data2]. The status byte encodes the message type and channel. Parsing these correctly is the critical path before forwarding to a Worker.

The Worker pipeline:
1. Parses the raw MIDI message into a structured event (NoteOn, NoteOff, CC, PitchBend, etc.).
2. POST the structured event to `/api/midi/event`.
3. Worker persists to D1 and optionally broadcasts via a Durable Object WebSocket connection.

---

## Feature Detection

```typescript
// src/midi/support.ts
export function isMIDISupported(): boolean {
  return (
    typeof navigator !== "undefined" &&
    "requestMIDIAccess" in navigator
  );
}
```

---

## MIDI Access and Port Management

```typescript
// src/midi/access.ts

export interface MIDIPortInfo {
  id: string;
  name: string | null;
  manufacturer: string | null;
  state: MIDIPortDeviceState;
  connection: MIDIPortConnectionState;
}

export async function getMIDIAccess(
  sysex = false
): Promise<MIDIAccess> {
  if (!isMIDISupported()) {
    throw new Error("Web MIDI API is not supported in this browser");
  }
  // requestMIDIAccess() triggers the permission prompt on first call
  return navigator.requestMIDIAccess({ sysex });
}

export function listInputPorts(access: MIDIAccess): MIDIPortInfo[] {
  const ports: MIDIPortInfo[] = [];
  access.inputs.forEach((input) => {
    ports.push({
      id: input.id,
      name: input.name ?? null,
      manufacturer: input.manufacturer ?? null,
      state: input.state,
      connection: input.connection,
    });
  });
  return ports;
}

export function isMIDISupported() {
  return typeof navigator !== "undefined" && "requestMIDIAccess" in navigator;
}
```

---

## MIDI Message Parser

```typescript
// src/midi/parser.ts

export type MIDIEventType =
  | "note_on"
  | "note_off"
  | "control_change"
  | "program_change"
  | "pitch_bend"
  | "aftertouch"
  | "poly_aftertouch"
  | "sysex"
  | "clock"
  | "unknown";

export interface ParsedMIDIEvent {
  type: MIDIEventType;
  channel: number | null; // 0-indexed (0–15), null for system messages
  note: number | null;
  velocity: number | null;
  controller: number | null;
  value: number | null;       // generic value for CC, pitch bend, program change
  rawBytes: number[];
  receivedAt: number;         // performance.now() timestamp
  portId: string;
  portName: string | null;
}

export function parseMIDIMessage(
  event: MIDIMessageEvent,
  portId: string,
  portName: string | null
): ParsedMIDIEvent {
  const data = event.data;
  const status = data[0];
  const type = status & 0xf0;
  const channel = status & 0x0f;

  const base: Omit<ParsedMIDIEvent, "type"> = {
    channel: null,
    note: null,
    velocity: null,
    controller: null,
    value: null,
    rawBytes: Array.from(data),
    receivedAt: event.timeStamp,
    portId,
    portName,
  };

  switch (type) {
    case 0x90: // Note On (velocity 0 is treated as Note Off by convention)
      return {
        ...base,
        type: data[2] === 0 ? "note_off" : "note_on",
        channel,
        note: data[1],
        velocity: data[2],
      };

    case 0x80: // Note Off
      return { ...base, type: "note_off", channel, note: data[1], velocity: data[2] };

    case 0xb0: // Control Change
      return { ...base, type: "control_change", channel, controller: data[1], value: data[2] };

    case 0xc0: // Program Change
      return { ...base, type: "program_change", channel, value: data[1] };

    case 0xe0: // Pitch Bend (-8192 to +8191)
      return {
        ...base,
        type: "pitch_bend",
        channel,
        value: ((data[2] << 7) | data[1]) - 8192,
      };

    case 0xa0: // Poly Aftertouch
      return { ...base, type: "poly_aftertouch", channel, note: data[1], value: data[2] };

    case 0xd0: // Channel Aftertouch
      return { ...base, type: "aftertouch", channel, value: data[1] };

    case 0xf0: // System messages
      if (status === 0xf8) return { ...base, type: "clock" };
      if (status === 0xf0) return { ...base, type: "sysex" };
      return { ...base, type: "unknown" };

    default:
      return { ...base, type: "unknown" };
  }
}
```

---

## MIDI Listener

```typescript
// src/midi/listener.ts
import { parseMIDIMessage, type ParsedMIDIEvent } from "./parser";

export type MIDIEventCallback = (event: ParsedMIDIEvent) => void;

export function attachMIDIListeners(
  access: MIDIAccess,
  onEvent: MIDIEventCallback
): () => void {
  const handlers = new Map<string, (e: Event) => void>();

  function attachToInput(input: MIDIInput) {
    const handler = (e: Event) => {
      const midiEvent = e as MIDIMessageEvent;
      onEvent(parseMIDIMessage(midiEvent, input.id, input.name ?? null));
    };
    input.addEventListener("midimessage", handler);
    handlers.set(input.id, handler);
  }

  access.inputs.forEach(attachToInput);

  // Re-attach when ports are hot-plugged
  const stateChangeHandler = () => {
    access.inputs.forEach((input) => {
      if (!handlers.has(input.id)) {
        attachToInput(input);
      }
    });
  };

  access.addEventListener("statechange", stateChangeHandler);

  return () => {
    access.inputs.forEach((input) => {
      const handler = handlers.get(input.id);
      if (handler) input.removeEventListener("midimessage", handler);
    });
    access.removeEventListener("statechange", stateChangeHandler);
    handlers.clear();
  };
}
```

---

## Forwarding to a Cloudflare Worker (batched)

```typescript
// src/midi/pipeline.ts
import type { ParsedMIDIEvent } from "./parser";

const BATCH_INTERVAL_MS = 200;   // flush every 200ms
const BATCH_MAX_SIZE    = 50;    // or when 50 events accumulate

export class MIDIEventPipeline {
  private queue: ParsedMIDIEvent[] = [];
  private timer: ReturnType<typeof setTimeout> | null = null;
  private sessionId: string;

  constructor(sessionId: string) {
    this.sessionId = sessionId;
  }

  enqueue(event: ParsedMIDIEvent): void {
    // Drop MIDI clock events from the pipeline — they fire 24x per beat
    if (event.type === "clock") return;
    this.queue.push(event);

    if (this.queue.length >= BATCH_MAX_SIZE) {
      this.flush();
    } else if (!this.timer) {
      this.timer = setTimeout(() => this.flush(), BATCH_INTERVAL_MS);
    }
  }

  private async flush(): Promise<void> {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    if (this.queue.length === 0) return;

    const batch = this.queue.splice(0);
    try {
      await fetch("/api/midi/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId: this.sessionId, events: batch }),
        // keepalive ensures the request completes even if the page closes
        keepalive: true,
      });
    } catch (err) {
      console.warn("MIDI pipeline flush failed:", err);
    }
  }

  destroy(): void {
    this.flush();
  }
}
```

---

## Cloudflare Pages Function — `/api/midi/events`

```typescript
// functions/api/midi/events.ts
import type { PagesFunction } from "@cloudflare/workers-types";

interface Env {
  MIDI_DB: D1Database;
}

interface MIDIEventBatch {
  sessionId: string;
  events: Array<{
    type: string;
    channel: number | null;
    note: number | null;
    velocity: number | null;
    controller: number | null;
    value: number | null;
    receivedAt: number;
    portId: string;
    portName: string | null;
  }>;
}

export const onRequestPost: PagesFunction<Env> = async ({ request, env }) => {
  let body: MIDIEventBatch;
  try {
    body = (await request.json()) as MIDIEventBatch;
  } catch {
    return Response.json({ message: "Invalid JSON" }, { status: 400 });
  }

  if (!body.sessionId || !Array.isArray(body.events)) {
    return Response.json({ message: "Missing sessionId or events" }, { status: 422 });
  }

  // Cap at 100 events per batch
  const events = body.events.slice(0, 100);

  const stmt = env.MIDI_DB.prepare(
    `INSERT INTO midi_events
       (id, session_id, type, channel, note, velocity, controller, value, received_at, port_id, port_name)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
  );

  const batch = events.map((e) =>
    stmt.bind(
      crypto.randomUUID(),
      body.sessionId,
      e.type,
      e.channel,
      e.note,
      e.velocity,
      e.controller,
      e.value,
      e.receivedAt,
      e.portId,
      e.portName
    )
  );

  await env.MIDI_DB.batch(batch);

  return Response.json({ stored: events.length }, { status: 201 });
};
```

---

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS midi_events (
  id          TEXT PRIMARY KEY,
  session_id  TEXT NOT NULL,
  type        TEXT NOT NULL,
  channel     INTEGER,
  note        INTEGER,
  velocity    INTEGER,
  controller  INTEGER,
  value       INTEGER,
  received_at REAL NOT NULL,       -- performance.now() ms
  port_id     TEXT NOT NULL,
  port_name   TEXT
);

CREATE INDEX idx_midi_session ON midi_events (session_id, received_at);
CREATE INDEX idx_midi_type    ON midi_events (type, received_at);
```

---

## Anti-patterns

- **Posting every MIDI message as a separate fetch.** MIDI can fire hundreds of events per second (especially clock, pitch bend sweeps, and CC faders). Always batch before sending to the Worker.
- **Not filtering MIDI clock messages.** `0xf8` (MIDI clock) fires 24 times per beat at any tempo. A 120 BPM session generates 48 clock messages per second. Drop them from the pipeline unless you specifically need them.
- **Treating Note On with velocity 0 as Note On.** The MIDI spec defines velocity-0 Note On as equivalent to Note Off. Many keyboards use this instead of the 0x80 Note Off status. The parser above handles this; don't assume.
- **Not removing `midimessage` listeners on component unmount.** MIDI inputs are global browser resources; dangling listeners continue firing.
- **Requesting `sysex: true` unless strictly necessary.** SysEx grants access to manufacturer-specific messages and can expose sensitive device data. Request it only when your application explicitly handles SysEx payloads.

---

## Gotchas

- On macOS, Chrome requires the user to grant MIDI access the first time. Some macOS security policies also block third-party MIDI drivers from appearing in `access.inputs`. Instruct users to check System Settings → Privacy → MIDI.
- `navigator.requestMIDIAccess()` returns a Promise; the port list is only available after the promise resolves, not immediately.
- MIDI input ports may appear with state `"connected"` but connection `"closed"`. Call `port.open()` explicitly if you need guaranteed connection before reading.
- `MIDIMessageEvent.data` is a `Uint8Array`. The length varies — SysEx messages can be arbitrarily long. Always check `data.length` before accessing `data[1]` or `data[2]`.
- `event.timeStamp` in a `midimessage` event is relative to `performance.timeOrigin` (same as `DOMHighResTimeStamp`), not a Unix timestamp. Store it as a relative offset if you care about in-session timing; convert to an absolute timestamp (`performance.timeOrigin + event.timeStamp`) for cross-session comparison.

---

## Verification

1. Open the Pages site in Chrome on desktop.
2. Connect a MIDI keyboard or controller via USB.
3. Call `navigator.requestMIDIAccess()` and confirm the permission dialog appears.
4. Check `access.inputs.size` in the console — it should be ≥ 1.
5. Play some notes and confirm `parseMIDIMessage` returns correct `type: "note_on"` and `note` values.
6. Watch the Network tab; confirm batched POSTs arrive at `/api/midi/events` every 200ms.
7. Query D1: `SELECT type, COUNT(*) FROM midi_events GROUP BY type;` to verify all event types are stored correctly.

---

## Related

- `web-audio-api` (not currently in KB)
- `websocket-durable-objects-realtime-ui.md`
- `web-serial-api-workers-device-bridge.md`
- `web-bluetooth-api-workers-device-bridge.md`
- `user-activation-transient-sticky-gating.md`

---

## Sources

- MDN Web MIDI API: https://developer.mozilla.org/en-US/docs/Web/API/Web_MIDI_API
- MIDI Association: https://www.midi.org/specifications
- W3C Web MIDI API Specification: https://webaudio.github.io/web-midi-api/
- Cloudflare D1 batch operations: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- Cloudflare Pages Functions: https://developers.cloudflare.com/pages/functions/
