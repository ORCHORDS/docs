# streaming-sse-testing

**Issue:** Streaming endpoints (SSE, chunked LLM responses, `ReadableStream`) return data in partial chunks across an open connection that most test clients collapse into one final string — hiding real bugs
**Date:** 2026-08-12
**Status:** documented

## Symptom / Context

You ship a `/chat` endpoint that streams tokens via Server-Sent Events. A manual test in the browser
looks fine. But in tests, `fetch('/chat')` buffers the whole body, so you only ever assert against
the final concatenated string. Bugs that slip through:
- the first chunk is never emitted (client shows blank until the whole response is done)
- chunks arrive in the wrong order on slow connections
- the `[DONE]` terminator is missing, so the client hangs waiting for more
- the heartbeat/keepalive comment (`: ping\n\n`) is malformed and the proxy drops the connection
- backpressure: a slow client causes unbounded memory growth because the stream is never paused
- an error mid-stream never sends an error event — the client just sees the stream end silently

## Pattern / Solution

Test the stream as a stream, not as a buffered string. Three layers.

### 1. Assert the raw bytes framing
Use a client that reads the body as a stream and inspects each `data:` line:
```ts
test("emits tokens as separate SSE events in order", async () => {
  const res = await fetch("/chat", { method: "POST", body: '{"q":"hi"}' });
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  const events: string[] = [];
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const frames = buf.split("\n\n");
    buf = frames.pop()!;              // keep partial frame
    for (const f of frames) events.push(f);
  }
  expect(events[0]).toMatch(/^data: /);          // first chunk is real data, not blank
  expect(events.at(-1)).toBe("data: [DONE]");    // terminator present
  expect(events.length).toBeGreaterThan(1);      // genuinely chunked, not one blob
});
```
The key assertions: (a) first event is data, (b) last event is `[DONE]`, (c) more than one event
arrived — otherwise the server is buffering and not actually streaming.

### 2. Assert timing and backpressure
Inject a slow consumer and verify the producer pauses instead of OOMing:
```ts
test("honours backpressure on slow reader", async () => {
  const res = await fetch("/chat");
  const reader = res.body!.getReader();
  await reader.read();              // read one chunk, then stall
  await wait(2000);                 // producer should pause, not buffer infinitely
  const memAfter = process.memoryUsage().heapUsed;
  expect(memAfter).toBeLessThan(BUDGET);   // define a real ceiling
  reader.cancel();
});
```
Also assert first-byte time (`res.body` first chunk) is under your SLA, not just total time.

### 3. Assert error and abort paths
- Mid-stream server error → client receives an `event: error` frame, not a silent close.
- Client aborts (`AbortController`) → server stops generating within a deadline (check logs/metrics,
  not just the client side).
- Connection drop → server cleans up resources (no leaked timer/stream handle). Verify with a
  post-test process snapshot.

## Gotchas

- `await fetch().then(r => r.text())` hides every streaming bug — it buffers. You MUST read from
  `r.body.getReader()` to test streaming behaviour at all.
- Node's built-in `fetch` (undici) and browser `fetch` chunk differently — test against the runtime
  you actually deploy, not just jsdom.
- SSE parsers split on `\n\n`, but a chunk boundary can land in the middle of a frame. Always keep
  the trailing partial frame in a buffer and re-feed it (shown above). Forgetting this causes
  intermittent "lost first/last event" bugs in tests.
- `Content-Type: text/event-stream` alone does not disable buffering — also set
  `X-Accel-Buffering: no` for nginx, and disable compression on that route, or proxies will buffer
  the whole stream and your "streaming" endpoint is suddenly not.
- `[DONE]` is an OpenAI convention, not part of the SSE spec — if clients expect it, assert it; if
  they expect the connection to close, assert close instead. Mixing the two causes client hangs.
- Heartbeats (`: ping\n\n`) are comments and will appear in your raw event list. Filter them before
  asserting on data events, or your count assertions will be off by one intermittently.
- Backpressure tests are flaky on shared CI runners where the event loop is contended — use generous
  bounds and prefer testing this in an environment that matches production.
- For LLM streaming, assert that partial JSON in each `data:` frame is parseable into a delta — a
  common bug is the server emitting whole objects instead of deltas, or vice versa.

## Related
- llm-evaluation-testing
- ai-agent-testing
- contract-timeout-and-cancellation-tests
- test-retry-strategies
- memory-leak-testing
- playwright-network-interception
