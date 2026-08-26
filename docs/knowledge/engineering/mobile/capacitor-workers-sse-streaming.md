# Server-Sent Events Streaming from Cloudflare Workers in Capacitor Apps

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
AI-generated text and live score updates delivered via Server-Sent Events (SSE) from a Cloudflare Worker stream correctly in a browser but stall or arrive in large batches on iOS and Android Capacitor apps due to WebView buffering or plugin limitations.

## Context
Capacitor's built-in `fetch` and `@capacitor/http` buffer the entire response before resolving, which breaks SSE streaming. On iOS, WKWebView has its own SSE buffering quirks. The reliable path is a native Capacitor plugin that opens a native `NSURLSession` (iOS) or `OkHttp` (Android) streaming connection and emits events to the WebView layer via Capacitor's event bridge.

## Cloudflare Worker — SSE Endpoint
```typescript
// workers/sse-stream.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== 'GET') return new Response('Method not allowed', { status: 405 });

    const url  = new URL(req.url);
    const topic = url.searchParams.get('topic') ?? 'default';
    const auth  = req.headers.get('Authorization') ?? '';
    if (!await validateBearer(auth, env)) return new Response('Unauthorized', { status: 401 });

    const { readable, writable } = new TransformStream();
    const writer = writable.getWriter();
    const enc    = new TextEncoder();

    // Keep-alive and event loop
    const pump = async () => {
      try {
        // Send retry hint to client
        await writer.write(enc.encode(`retry: 3000\n\n`));

        // Subscribe to Durable Object broadcast or KV polling
        const id = env.BROADCASTER.idFromName(topic);
        const stub = env.BROADCASTER.get(id);

        let eventId = 0;
        while (true) {
          const events = await stub.fetch(`https://internal/events?since=${eventId}`).then(r => r.json<{ id: number; data: string }[]>());
          for (const ev of events) {
            await writer.write(enc.encode(`id: ${ev.id}\ndata: ${ev.data}\n\n`));
            eventId = ev.id;
          }
          await new Promise(r => setTimeout(r, 500));  // poll interval
        }
      } catch {
        await writer.close();
      }
    };

    pump();   // fire-and-forget; Worker streams until client disconnects

    return new Response(readable, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Access-Control-Allow-Origin': '*',
        'X-Accel-Buffering': 'no',   // disable Nginx/proxy buffering if proxied
      },
    });
  },
};
```

## iOS Native Plugin — Swift SSE Reader
```swift
// ios/App/Plugins/SSEPlugin/SSEPlugin.swift
import Capacitor
import Foundation

@objc(SSEPlugin)
public class SSEPlugin: CAPPlugin, URLSessionDataDelegate {

    private var session: URLSession?
    private var activeTask: URLSessionDataTask?
    private var decoder = UTF8Decoder()

    @objc func subscribe(_ call: CAPPluginCall) {
        let urlStr = call.getString("url") ?? ""
        let token  = call.getString("token") ?? ""
        guard let url = URL(string: urlStr) else {
            call.reject("Invalid URL"); return
        }

        var request = URLRequest(url: url, timeoutInterval: TimeInterval.infinity)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        request.setValue("no-cache", forHTTPHeaderField: "Cache-Control")

        let cfg = URLSessionConfiguration.default
        cfg.requestCachePolicy = .reloadIgnoringLocalCacheData
        session = URLSession(configuration: cfg, delegate: self, delegateQueue: nil)
        activeTask = session?.dataTask(with: request)
        activeTask?.resume()
        call.resolve()   // resolve immediately; events arrive via notifyListeners
    }

    @objc func unsubscribe(_ call: CAPPluginCall) {
        activeTask?.cancel()
        session?.invalidateAndCancel()
        activeTask = nil
        session = nil
        call.resolve()
    }

    // URLSessionDataDelegate
    public func urlSession(_ session: URLSession,
                           dataTask: URLSessionDataTask,
                           didReceive data: Data) {
        guard let text = String(data: data, encoding: .utf8) else { return }
        parseSSE(text)
    }

    public func urlSession(_ session: URLSession, task: URLSessionTask,
                           didCompleteWithError error: Error?) {
        notifyListeners("sseClose", data: ["error": error?.localizedDescription ?? ""])
    }

    private func parseSSE(_ chunk: String) {
        // Split on double-newline (SSE event boundaries)
        chunk.components(separatedBy: "\n\n").forEach { block in
            var eventType = "message"
            var data = ""
            var id = ""
            block.components(separatedBy: "\n").forEach { line in
                if line.hasPrefix("event: ") { eventType = String(line.dropFirst(7)) }
                else if line.hasPrefix("data: ")  { data = String(line.dropFirst(6)) }
                else if line.hasPrefix("id: ")    { id   = String(line.dropFirst(4)) }
            }
            if !data.isEmpty {
                notifyListeners("sseMessage", data: ["event": eventType, "data": data, "id": id])
            }
        }
    }
}
```

## Android Native Plugin — Kotlin SSE Reader
```kotlin
// android/app/src/main/java/com/yourapp/plugins/SSEPlugin.kt
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import kotlinx.coroutines.*
import okhttp3.*
import okio.BufferedSource

@CapacitorPlugin(name = "SSEPlugin")
class SSEPlugin : Plugin() {

    private val client = OkHttpClient.Builder()
        .readTimeout(0, java.util.concurrent.TimeUnit.MILLISECONDS)  // no read timeout for SSE
        .build()

    private var job: Job? = null

    @PluginMethod
    fun subscribe(call: PluginCall) {
        val url   = call.getString("url") ?: run { call.reject("Missing url"); return }
        val token = call.getString("token") ?: ""

        job = CoroutineScope(Dispatchers.IO).launch {
            val request = Request.Builder()
                .url(url)
                .header("Authorization", "Bearer $token")
                .header("Accept", "text/event-stream")
                .header("Cache-Control", "no-cache")
                .build()

            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    notifyListeners("sseClose", JSObject().apply { put("error", "HTTP ${response.code}") })
                    return@use
                }
                val source: BufferedSource = response.body!!.source()
                val buffer = StringBuilder()
                while (!source.exhausted()) {
                    val line = source.readUtf8Line() ?: break
                    if (line.isEmpty()) {
                        // blank line = end of event
                        parseAndEmit(buffer.toString())
                        buffer.clear()
                    } else {
                        buffer.appendLine(line)
                    }
                }
            }
        }
        call.resolve()
    }

    @PluginMethod
    fun unsubscribe(call: PluginCall) {
        job?.cancel()
        job = null
        call.resolve()
    }

    private fun parseAndEmit(block: String) {
        var eventType = "message"; var data = ""; var id = ""
        block.trim().lines().forEach { line ->
            when {
                line.startsWith("event: ") -> eventType = line.removePrefix("event: ")
                line.startsWith("data: ")  -> data      = line.removePrefix("data: ")
                line.startsWith("id: ")    -> id        = line.removePrefix("id: ")
            }
        }
        if (data.isNotEmpty()) {
            notifyListeners("sseMessage", JSObject().apply {
                put("event", eventType); put("data", data); put("id", id)
            })
        }
    }
}
```

## Capacitor TypeScript Bridge
```typescript
// src/plugins/sse.ts
import { registerPlugin } from '@capacitor/core';

export interface SSEPlugin {
  subscribe(options: { url: string; token: string }): Promise<void>;
  unsubscribe(): Promise<void>;
  addListener(event: 'sseMessage', handler: (e: SSEEvent) => void): Promise<PluginListenerHandle>;
  addListener(event: 'sseClose',   handler: (e: { error: string }) => void): Promise<PluginListenerHandle>;
}
export interface SSEEvent { event: string; data: string; id: string }

export const SSEPlugin = registerPlugin<SSEPlugin>('SSEPlugin');

// React hook
export function useSSEStream(url: string, token: string | null) {
  const [messages, setMessages] = useState<SSEEvent[]>([]);

  useEffect(() => {
    if (!token) return;
    let listener: PluginListenerHandle;
    (async () => {
      await SSEPlugin.subscribe({ url, token });
      listener = await SSEPlugin.addListener('sseMessage', ev => {
        setMessages(prev => [...prev, ev]);
      });
    })();
    return () => {
      listener?.remove();
      SSEPlugin.unsubscribe();
    };
  }, [url, token]);

  return messages;
}
```

## Anti-patterns
- Using `EventSource` in the WebView via JavaScript — WKWebView silently buffers SSE chunks until a flush point; events arrive minutes late on iOS.
- Setting a finite `readTimeout` on OkHttp — SSE connections are long-lived; a 30 s timeout kills the stream between server events.
- Emitting a new `notifyListeners` call per byte — buffer complete events (double-newline delimiter) before emitting.
- Parsing the entire Cloudflare Worker response as JSON — SSE is a text protocol; parse line-by-line.
- Leaving the connection open after the Capacitor view is destroyed — always cancel the OkHttp call / URLSessionTask in `unsubscribe`.

## Gotchas
- Cloudflare Workers stream via `TransformStream`; the edge compresses by default. Add `Content-Encoding: identity` or disable compression in the Worker to avoid chunk fragmentation.
- iOS 16 and earlier require `X-Accel-Buffering: no` to be forwarded if any intermediate proxy (e.g., Cloudflare's own buffer) is in the path.
- Android's `OkHttpClient` is not thread-safe to share between plugin instances; instantiate one per plugin lifecycle.
- The Capacitor event bridge serialises payloads as JSON — do not put raw binary data in SSE `data:` fields; base64-encode if needed.

## Verification
1. Connect a device to Charles Proxy and confirm SSE chunks arrive every ~500 ms, not all at once.
2. Send 100 SSE events in rapid succession from the Worker and assert the Capacitor listener fires 100 times (not batched into one).
3. Background the app and foreground it — the stream should auto-reconnect (using the `retry:` hint).
4. Kill the Worker-side broadcaster and confirm `sseClose` fires within the `readTimeout`.

## Related
- [react-native-durable-objects-realtime.md](react-native-durable-objects-realtime.md)
- [mobile-websocket-realtime-connections.md](mobile-websocket-realtime-connections.md)
- [capacitor-http-plugin-workers-cors.md](capacitor-http-plugin-workers-cors.md)
- [capacitor-native-bridge-plugin-development.md](capacitor-native-bridge-plugin-development.md)
- [cloudflare-workers-response-streaming-mobile-buffer-limits.md](cloudflare-workers-response-streaming-mobile-buffer-limits.md)

## Sources
- MDN EventSource / SSE spec: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events
- Cloudflare Workers streaming: https://developers.cloudflare.com/workers/examples/streaming-responses/
- OkHttp streaming: https://square.github.io/okhttp/recipes/#response-body-streaming
- Capacitor Plugin development: https://capacitorjs.com/docs/plugins/creating-plugins
