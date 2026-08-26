# Cloudflare Pub/Sub MQTT Workers — Real-Time Event Fan-Out

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You need lightweight, standards-based publish/subscribe messaging at the edge without running a dedicated broker. Cloudflare Pub/Sub exposes an MQTT 5.0-compatible broker where Workers act as on-publish hooks, letting you inspect, transform, drop, or fan-out every message before it is delivered to subscribers.

## Context

Cloudflare Pub/Sub is a managed MQTT 5.0 broker hosted on Cloudflare's network. Each broker namespace contains topics; clients connect via MQTT over WebSockets or raw TCP (port 8883 TLS). The key integration point is the **on-publish hook**: when a message arrives at the broker, Cloudflare invokes a Worker before delivering it. The Worker receives a batch of MQTT messages, can mutate or reject them, and returns the modified batch. This makes Pub/Sub suitable for IoT telemetry pipelines, real-time dashboards, and fan-out notification systems without any external infrastructure.

## Provisioning a Broker and Namespace

```typescript
// wrangler.toml binding (after creating broker via wrangler pubsub)
// [[pubsub]]
// name = "MY_BROKER"
// namespace = "prod"

// Broker URL: mqtts://MY_BROKER.YOUR_NAMESPACE.cloudflarepubsub.com:8883

// Generate client credentials via CLI:
// wrangler pubsub broker create my-broker --namespace=prod
// wrangler pubsub broker issue-credentials my-broker \
//   --number=5 --expiration=43200 --namespace=prod
```

The broker URL follows the pattern `<broker>.<namespace>.cloudflarepubsub.com`. Credentials are short-lived JWTs issued per client so rotation is straightforward.

## On-Publish Hook Worker

```typescript
export interface Env {
  ALLOWED_TOPIC_PREFIX: string; // e.g. "sensors/"
}

interface PubSubMessage {
  readonly mid: number;
  readonly topic: string;
  readonly contentType: string;
  readonly payloadFormatIndicator: number;
  readonly clientId: string;
  readonly receivedAt: number;
  readonly payload: string; // base64-encoded
  readonly retain: boolean;
  readonly qos: 0 | 1;
  jwtPayload?: Record<string, unknown>;
}

interface PubSubOnPublishBody {
  readonly broker: string;
  readonly namespace: string;
  readonly messages: PubSubMessage[];
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Cloudflare sends a POST with the message batch
    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    const incomingAuth = request.headers.get("X-Pub-Sub-Webhook-Auth");
    if (!incomingAuth || !isValidSignature(incomingAuth, env)) {
      return new Response("Unauthorized", { status: 403 });
    }

    let body: PubSubOnPublishBody;
    try {
      body = await request.json<PubSubOnPublishBody>();
    } catch {
      return new Response("Bad request", { status: 400 });
    }

    const allowedPrefix = env.ALLOWED_TOPIC_PREFIX;
    const filtered: PubSubMessage[] = [];

    for (const msg of body.messages) {
      // Drop messages not matching the allowed topic prefix
      if (!msg.topic.startsWith(allowedPrefix)) {
        console.warn(`Dropping message on disallowed topic: ${msg.topic}`);
        continue;
      }

      // Decode and validate payload (IoT telemetry example)
      const raw = atob(msg.payload);
      let data: Record<string, unknown>;
      try {
        data = JSON.parse(raw) as Record<string, unknown>;
      } catch {
        console.error(`Non-JSON payload on ${msg.topic}, dropping`);
        continue;
      }

      // Enrich with server-side timestamp
      data.__serverTs = Date.now();
      data.__clientId = msg.clientId;

      // Re-encode the mutated payload
      const enriched: PubSubMessage = {
        ...msg,
        payload: btoa(JSON.stringify(data)),
        contentType: "application/json",
      };
      filtered.push(enriched);
    }

    // Return the modified batch; Cloudflare delivers only what you return
    return Response.json({ messages: filtered });
  },
};

function isValidSignature(header: string, env: Env): boolean {
  // In production, verify HMAC-SHA256 of request body against shared secret
  // stored in a Workers Secret. Simplified here for clarity.
  return header.startsWith("v1=");
}
```

## Publishing from a Worker (MQTT Client via Fetch)

```typescript
// Pub/Sub REST API lets Workers publish without opening a TCP connection
export async function publishSensorReading(
  topic: string,
  payload: Record<string, unknown>,
  brokerUrl: string,
  apiToken: string
): Promise<void> {
  const endpoint = `${brokerUrl}/publish`;
  const body = JSON.stringify({
    messages: [
      {
        topic,
        payload: btoa(JSON.stringify(payload)),
        content_type: "application/json",
      },
    ],
  });

  const res = await fetch(endpoint, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiToken}`,
      "Content-Type": "application/json",
    },
    body,
  });

  if (!res.ok) {
    throw new Error(`Pub/Sub publish failed: ${res.status} ${await res.text()}`);
  }
}
```

## Fanout to Durable Objects via On-Publish Hook

```typescript
// Extend the hook to fan out aggregated readings to a DO per device
import type { DurableObjectNamespace } from "@cloudflare/workers-types";

export interface Env {
  ALLOWED_TOPIC_PREFIX: string;
  DEVICE_STATE: DurableObjectNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const body = await request.json<PubSubOnPublishBody>();
    const ctx = request as unknown as ExecutionContext;

    for (const msg of body.messages) {
      const deviceId = msg.topic.split("/")[1]; // e.g. "sensors/<deviceId>/temp"
      if (!deviceId) continue;

      const id = env.DEVICE_STATE.idFromName(deviceId);
      const stub = env.DEVICE_STATE.get(id);

      // Fire-and-forget state update; do NOT await in the hot path
      ctx.waitUntil(
        stub.fetch("https://internal/update", {
          method: "POST",
          body: msg.payload,
          headers: { "Content-Type": "application/json" },
        })
      );
    }

    return Response.json({ messages: body.messages });
  },
};
```

## Anti-patterns

- Awaiting slow side-effects (e.g. database writes) inside the on-publish hook synchronously — use `ctx.waitUntil` to avoid adding latency to every subscriber delivery.
- Using Pub/Sub for large binary blobs; MQTT has a default 256 KB message limit — store blobs in R2 and publish the key instead.
- Hardcoding broker credentials in Worker source; always use Wrangler Secrets or the Secrets Store binding.

## Gotchas

- The on-publish Worker **must** return the message batch within 10 seconds or Cloudflare treats it as an error and delivers the original unmodified batch.
- MQTT QoS 2 (exactly-once) is not supported; only QoS 0 (at-most-once) and QoS 1 (at-least-once) are available.

## Verification

```bash
# Create broker and issue test credentials
wrangler pubsub broker create telemetry --namespace=prod
wrangler pubsub broker issue-credentials telemetry \
  --number=1 --expiration=3600 --namespace=prod

# Publish a test message via mosquitto_pub
mosquitto_pub \
  -h "telemetry.prod.cloudflarepubsub.com" \
  -p 8883 \
  --tls-use-os-certs \
  -u "client1" \
  -P "<JWT_CREDENTIAL>" \
  -t "sensors/dev42/temp" \
  -m '{"celsius":22.5}' \
  -q 1

# Check Worker logs for the enriched payload
wrangler tail --format=pretty
```

## Related

- `cloudflare/durable-objects-real-time-state.md`
- `cloudflare/cloudflare-queues-dead-letter-dlq.md`
- `cloudflare/workers-rpc-service-binding-patterns.md`

## Sources

- https://developers.cloudflare.com/pub-sub/
- https://developers.cloudflare.com/pub-sub/learning/integrate-workers/
- https://developers.cloudflare.com/pub-sub/platform/mqtt-compatibility/
