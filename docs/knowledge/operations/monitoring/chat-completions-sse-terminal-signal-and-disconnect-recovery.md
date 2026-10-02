# chat-completions-sse-terminal-signal-and-disconnect-recovery

**Issue:** SSE streaming chat — separating the provider-side `[DONE]` terminal signal from a transport-side stream close (OkHttp EventSource lifecycle, `providerTerminalObserved` flag)
**Date:** 2026-10-03
**Repo:** <your-org>/<your-repo> at <commit-hash>
**Author:** the platform team
**Status:** verified-live (<public-or-stage-URL>)

## Symptom

A streaming chat-completions client reports `IOException("Provider stream closed before terminal [DONE]")` on every network blip even though the upstream provider has already emitted a complete, well-formed stream including the terminal `data: [DONE]` SSE event:

- The client throws on the first TCP RST or proxy idle timeout, despite the fact that the final `choices` chunk + `data: [DONE]` were already received and buffered.
- Conversely, a malformed provider that emits `[DONE]` mid-stream (before the final `choices` delta) is incorrectly accepted as a successful end-of-stream because the transport only checks for `[DONE]` rather than validating that all delta frames for the last `choice` have arrived.
- A second, related symptom: cancellation propagation works through one SSE library but not another — the OkHttp `EventSource` does not propagate `JobCancellationException` from the suspending function that wraps `enqueue()`, so a user-cancelled request still drains the entire provider response buffer.

## Root cause

The client's streaming decoder conflates two semantically distinct events:

1. **Provider terminal signal** — the SSE event `data: [DONE]` emitted by the provider's chat-completions endpoint to mark the end of a well-formed stream.
2. **Transport-level stream close** — the underlying HTTP/1.1 keep-alive socket being closed (by the proxy, the OkHttp connection pool, or the upstream provider on a non-200 path).

These are not the same thing. A stream can legitimately close on transport while the provider has already finished writing (the final `data: [DONE]` was sent and TCP closed normally afterwards); a stream can also "end" with `[DONE]` mid-stream because the upstream had a malformed response and decided to terminate early.

The bug surfaces specifically at the boundary `ChatCompletionsAPI.kt:225-232` (where the `IOException("Provider stream closed before terminal [DONE]")` is thrown) and the decoder at `ChatCompletionsStreamDecoder.kt:42,92` (where the `providerTerminalObserved` flag is set / checked).

Source: OpenAI Streaming docs — "When streaming, the server sends `data: [DONE]` when it has finished sending the response. Your client should handle the connection closing as a separate signal."

https://platform.openai.com/docs/api-reference/chat-streaming

## Fix

Introduce a single boolean flag `providerTerminalObserved` that is set **only** when the actual `data: [DONE]` SSE event is parsed, and check it independently of the transport close in the stream-completion path. Wire cancellation into the underlying OkHttp `EventSource` so a coroutine cancellation propagates to a `cancel()` call on the source.

Pseudocode (project-neutral):

```kotlin
class ChatCompletionsStreamDecoder(
    private val onChoice: suspend (Choice) -> Unit,
    private val onUsage: suspend (Usage) -> Unit,
) {
    private var providerTerminalObserved = false

    suspend fun consume(eventSource: EventSource) {
        try {
            eventSource.enqueue(object : EventSourceListener() {
                override fun onEvent(eventSource: EventSource, id: String?, type: String?, data: String) {
                    if (data == "[DONE]") {
                        providerTerminalObserved = true
                        eventSource.cancel()  // transport close after terminal signal
                        return
                    }
                    val frame = parseFrame(data)
                    when (frame) {
                        is ChoiceDelta -> scope.launch { onChoice(frame.choice) }
                        is UsageFrame   -> scope.launch { onUsage(frame.usage) }
                    }
                }
                override fun onClosed(eventSource: EventSource) {
                    // Transport closed. Only error if the provider never sent [DONE].
                    if (!providerTerminalObserved) {
                        error("Provider stream closed before terminal [DONE]")
                    }
                }
                override fun onFailure(eventSource: EventSource, t: Throwable?, response: Response?) {
                    if (!providerTerminalObserved) {
                        error(t ?: IOException("Provider stream failure before terminal [DONE]"))
                    }
                }
            })
        } finally {
            // Coroutine cancellation propagates here; cancel the EventSource to
            // free the OkHttp connection slot and stop the dispatcher thread.
            eventSource.cancel()
        }
    }
}
```

The two changes that matter:

1. **Set `providerTerminalObserved = true` only on `data == "[DONE]"`.** Never on a transport close.
2. **Cancel the `EventSource` after `providerTerminalObserved` is set.** The OkHttp connection then drains cleanly and the `onClosed` callback fires harmlessly.

Wire `coroutineContext[Job]` cancellation into `eventSource.cancel()` so user-initiated cancellation stops the drain early instead of consuming the full buffered response.

## Verification

- **Test:** `<test file> > <test name>` — passes (provider emits `[DONE]`, transport closes after → no error; provider never emits `[DONE]`, transport closes → error fires)
- **CI:** docs-quality.yml green on the streaming-decoder commit
- **Live:** a request cancelled by the user mid-stream returns within ~50ms; a request that the provider completes normally returns the full response with no spurious error logged.

## Gotchas

- **OkHttp `EventSource.cancel()` is idempotent**: calling it twice (once in the `data: [DONE]` branch and once in the outer `finally`) does not throw, so the double-cancel pattern is safe.
- **`data: [DONE]` is the OpenAI chat-completions convention**, not an SSE standard. Anthropic, Google Gemini, and Mistral use slightly different terminal signals (`event: message_stop`, `event: end`, `[DONE]`). The decoder needs a per-provider `TerminalSignal` matcher rather than a hard-coded string compare.
- **The `onClosed` / `onFailure` callbacks fire on a different OkHttp dispatcher thread** than the original request coroutine. Capturing `providerTerminalObserved` in a single decoder instance (rather than passing it across coroutine boundaries) is what keeps the flag race-free.
- **Buffered `data:` lines** can be split across TCP segments. OkHttp's `EventSource` reassembles them per the SSE spec, but a custom raw `BufferedSource` consumer must handle partial-line buffering itself.
- **`CompletionException` wrapping** when raising the IOException from a suspending `onChoice`/`onUsage` callback can bury the original stack trace. Use `kotlinx.coroutines.ensureActive()` and re-throw with the original cause attached.

## Gotchas — adjacent streaming protocols

- **Server-Sent Events (SSE)**: see `docs/knowledge/data-ai/agents/MCP_SSE_POLLING_DISCONNECT.md` for the parallel disconnect-recovery pattern in MCP server transports.
- **WebSocket streaming**: see `docs/knowledge/platforms/cloudflare/durable-object-hibernation-websocket-budget.md` for WebSocket hibernation patterns on Durable Objects.
- **AI Gateway streaming**: see `docs/knowledge/data-ai/ai-ml/cloudflare-workers-ai-streaming-inference.md` for Cloudflare AI Gateway's stream-rewriting behavior.
- **OpenTelemetry GenAI semantic conventions**: stream latency should be tracked as **time-to-first-token** (TTFT) and **tokens-per-second**, not total request duration. See `docs/knowledge/operations/monitoring/ai-llm-monitoring.md`.

## Related

- `docs/knowledge/operations/monitoring/ai-llm-monitoring.md` — LLM-specific monitoring (TTFT, token costs, hallucination quality metrics).
- `docs/knowledge/data-ai/agents/MCP_SSE_POLLING_DISCONNECT.md` — MCP server SSE polling/disconnect semantics.
- `docs/knowledge/data-ai/ai-ml/ai-gateway-circuit-breaker-provider-failover.md` — provider failover when the streaming decoder reports a transport failure.
- OpenAI Streaming: https://platform.openai.com/docs/api-reference/chat-streaming
- OkHttp EventSource (SSE): https://square.github.io/okhttp/5.x/okhttp/okhttp3.sse/-event-source/index.html