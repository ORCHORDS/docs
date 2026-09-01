# WebTransport HTTP3 Datagram And Session Data Types

## Scope

Choosing between WebTransport's two data-carrying types — unreliable datagrams and reliable, flow-controlled streams — within one HTTP/3 session. Covers the `WebTransportDatagramDuplexStream` (`datagrams.readable`/`writable`), unidirectional and bidirectional stream creation and acceptance, backpressure via `desiredSize`, datagram size limits, and session lifecycle promises (`ready`, `closed`, `draining`). Excludes server-side Durable Objects relay architecture (covered by the Workers WebTransport article in this leaf) and excludes WebRTC data channels as an alternative.

## Workflow or implementation guidance

A WebTransport session is one HTTP/3 connection carrying independent data types side by side. Datagrams are fire-and-forget frames: no delivery guarantee, no ordering, capped near the QUIC maximum datagram payload. Streams are the same QUIC streams HTTP/3 itself uses: reliable, ordered within the stream, flow-controlled, and cheap to open (no TCP-style head-of-line coupling — one blocked stream does not stall the others).

Datagrams are the right type when the newest value makes the old one worthless: cursor positions, presence pings, game input ticks, live meter readings. The duplex surface is plain streams:

```js
const session = new WebTransport('https://wt.example.com/live');
await session.ready;

const writer = session.datagrams.writable.getWriter();
await writer.write(encodeCursor(x, y));   // ~16 bytes, may be dropped, never retrried
writer.releaseLock();

const reader = session.datagrams.readable.getReader();
const { value, done } = await reader.read(); // Uint8Array or done on close
```

Datagram budget is the binding constraint. `session.datagrams.maxDatagramSize` (or the incoming/outgoing variants per direction where implemented) reports the payload ceiling — on the order of 1200 bytes after QUIC/TP framing, varying with path MTU and TLS overhead. Sending larger writes fails or throws depending on implementation; the discipline is: encode to a fixed small record, never fragment datagrams yourself (fragmentation re-invents reliability on top of the unreliable type — if you need it, use a stream), and include a sequence or timestamp in the payload because ordering is not preserved.

Streams carry everything that must arrive: chat text, state deltas, file chunks, RPC frames.

```js
// client-opened unidirectional stream: client sends, server reads
const uni = await session.createUnidirectionalStream();
const w = uni.getWriter();
await w.write(encodeEvent('join', roomId));
await w.close();

// bidirectional: request/response on one stream
const bidi = await session.createBidirectionalStream();
await bidi.writable.getWriter().write(encodeRequest(chunkId));
const { value } = await bidi.readable.getReader().read();
```

Incoming streams arrive on `incomingUnidirectionalStreams` / `incomingBidirectionalStreams` as streams-of-streams, each a `ReadableStream` whose values are themselves streams. A fan-out loop per session is the standard consumer:

```js
(async () => {
  const reader = session.incomingUnidirectionalStreams.getReader();
  while (true) {
    const { value: stream, done } = await reader.read();
    if (done) return;
    handleIncoming(stream);
  }
})();
```

Backpressure on streams is the writer's `desiredSize`: positive means the remote granted window, approaching/under zero means stop pushing. Honoring it is what keeps a fast sender from ballooning a slow receiver's memory:

```js
const w = bidi.getWriter();
for (const chunk of chunks) {
  if (w.desiredSize !== null && w.desiredSize <= 0) await w.ready;
  await w.write(chunk);
}
```

Datagrams have no backpressure signal at all — writes are send-and-forget, and congestion control is entirely the transport's business. Sustained datagram sending should be rate-limited by the application (a tick interval, not a tight loop), because loss under congestion is normal and retransmission is exactly what the type promises not to do.

Session lifecycle is promise-shaped and must be observed: `session.ready` resolves once the handshake completes (await it before first use); `session.draining` resolves when the server announced graceful shutdown via the CLOSE_WEBTRANSPORT_SESSION capsule (finish in-flight streams, reconnect soon); `session.closed` resolves/rejects when the session is fully gone — the reconnect trigger. `session.close({closeCode, reason})` shuts down from the client with an application code, which the server sees as the session's close info.

Type selection as a one-line policy: datagrams for state that expires, streams for state that accumulates. A hybrid is normal — presence on datagrams, chat on streams — multiplexed over the single session with no cross-type interference.

## Controls

- Encode datagram payloads to a fixed compact record well under `maxDatagramSize`, with an embedded sequence/timestamp; never fragment datagrams.
- One persistent session per endpoint pair, not per message; reuse it for both types and reconnect on `closed`.
- Honor `desiredSize` / `writer.ready` on all stream writes; add an application-level frame ack only when the transport contract is insufficient.
- Consume `incomingUnidirectionalStreams`/`incomingBidirectionalStreams` with a durable fan-out loop started right after `ready`.
- Treat `draining` as a soft deadline: flush and re-establish before `closed` fires.

## Validation evidence

- Loss/throughput test under `chrome://webrtc-internals`-style or DevTools network throttling with packet loss emulation: assert cursor-state datagrams degrade to stale-but-recent (fresh wins) while stream chat messages all arrive, proving the type split behaves under loss.
- Datagram size boundary test: send payloads at `maxDatagramSize` and one byte larger; assert the larger write throws or is dropped and the app surfaces it, pinning the ceiling in CI.
- Backpressure test: a slow consumer (reader with delays) against a fast producer honoring `desiredSize`; assert producer-side pending bytes stay bounded and the session does not reset.
- Lifecycle test: server-initiated draining then close; assert the client's `draining` → flush → reconnect sequence completes with no lost stream frames and datagram traffic resumed on the new session.

## Failure modes and correction

- Large datagram writes fail: payload exceeds the datagram size limit. Split the feature across a stream, or shrink the record — never hand-roll fragmentation over datagrams.
- Stream stalls with no error: writer ignored `desiredSize` and exhausted the remote flow-control window. Await `writer.ready` when the size hits zero.
- Missed server pushes: the `incomingUnidirectionalStreams` loop started late or crashed — streams buffer until read, but a crashed loop leaks them; wrap the loop and restart it on error with a logged restart counter.
- Session "hangs" before any traffic: `ready` was never awaited and the first write raced the handshake. Await `ready` unconditionally after construction.
- Silent reconnect storms: `closed` rejected and every retry also fails fast; the server rejected the upgrade (wrong path, missing session establishment headers) — inspect the rejection's `closeCode`/`reason` and back off exponentially rather than looping.
- Stale datagram rendering (jumpy cursors): the app renders whatever arrives last; add sequence-number discard so an out-of-order older datagram cannot overwrite a newer one.

## Limitations

- Datagram support requires HTTP/3 with the datagram extension enabled on the whole path; intermediaries that downgrade to HTTP/2 or strip the extension silently remove the datagram type (the duplex stream then errors or never yields).
- No delivery, ordering, or duplicate guarantees on datagrams, and no per-datagram ack surface — observability into loss must be built into the payload.
- `maxDatagramSize` is path-dependent and can change; read it per session rather than hardcoding.
- Reliable-unordered delivery sits between the two types and is not exposed by this API surface; partial-reliability needs must be approximated (sequence-discard on streams or application acks on datagrams).
- Support is uneven across engines; feature-detect `window.WebTransport` and the datagram duplex presence, and keep a WebSocket fallback path for the reliable type.

## Canonical sources

- W3C, WebTransport API: https://w3c.github.io/webtransport/
- IETF, HTTP/3 datagrams (RFC 9297): https://www.rfc-editor.org/rfc/rfc9297
- IETF, QUIC transport (RFC 9000), datagram frames context: https://www.rfc-editor.org/rfc/rfc9000
- MDN, `WebTransport` datagrams: https://developer.mozilla.org/en-US/docs/Web/API/WebTransport/datagrams
