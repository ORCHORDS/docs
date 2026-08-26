# Push Notification Personalization: Workers AI Sentiment-Based Copy Generation

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

---

## Symptom / Use-Case

Your push notifications have a 4% open rate. A/B tests show that users who received personalised copy — matching the emotional tone of their in-app activity — open 2–3× more. You have a Cloudflare Workers backend already sending notifications through APNs/FCM. You want to run a language model at the edge to rewrite notification copy based on each user's recent sentiment signals without adding latency or standing up a separate ML server.

---

## Context

Cloudflare Workers AI provides inference endpoints available inside Workers with no cold-start and sub-100ms median latency for small text classification and generation models. The pipeline is:

1. An event (order placed, message received, friend joined) triggers a push notification job via Cloudflare Queues.
2. A Queue consumer Worker fetches recent user signals (last 5 in-app events, preferred tone from KV) and calls Workers AI to classify sentiment and generate contextually appropriate copy.
3. The generated title and body are sent to APNs (iOS) or FCM (Android) via the existing delivery Worker.

This runs entirely within the Cloudflare network — no egress to a third-party LLM provider, no extra latency hop.

---

## 1. Queue Consumer Architecture

```typescript
// workers/notification-personalizer/src/index.ts
import { Ai } from "@cloudflare/ai";

export interface Env {
  AI: Ai;
  USER_SIGNALS: KVNamespace;
  APNS_TOKEN: string;
  FCM_KEY: string;
  NOTIFICATION_QUEUE: Queue;
}

export interface NotificationJob {
  userId: string;
  platform: "ios" | "android";
  deviceToken: string;
  eventType: string;              // "order_ready" | "new_message" | "friend_joined" | …
  eventPayload: Record<string, unknown>;
  defaultTitle: string;
  defaultBody: string;
}

export default {
  async queue(
    batch: MessageBatch<NotificationJob>,
    env: Env
  ): Promise<void> {
    await Promise.all(
      batch.messages.map((msg) => processJob(msg.body, env).then(() => msg.ack()))
    );
  },
};
```

---

## 2. Signal Fetching and Sentiment Classification

```typescript
// workers/notification-personalizer/src/personalize.ts
import { Ai } from "@cloudflare/ai";
import type { Env, NotificationJob } from "./index";

interface UserSignals {
  recentEvents: Array<{ type: string; ts: number; label?: string }>;
  preferredTone: "friendly" | "formal" | "minimal";
  language: string;
}

export async function fetchUserSignals(
  userId: string,
  env: Env
): Promise<UserSignals> {
  const raw = await env.USER_SIGNALS.get(`signals:${userId}`, "json");
  return (raw as UserSignals) ?? {
    recentEvents: [],
    preferredTone: "friendly",
    language: "en",
  };
}

export async function classifySentiment(
  recentEvents: UserSignals["recentEvents"],
  ai: Ai
): Promise<"positive" | "neutral" | "frustrated"> {
  if (!recentEvents.length) return "neutral";

  const text = recentEvents
    .slice(-5)
    .map((e) => e.label ?? e.type)
    .join(". ");

  const result = await ai.run("@cf/huggingface/distilbert-sst-2-int8", {
    text,
  });

  // DistilBERT SST-2 returns [{label: "POSITIVE"|"NEGATIVE", score}]
  const top = result[0];
  if (top.score < 0.6) return "neutral";
  return top.label === "POSITIVE" ? "positive" : "frustrated";
}
```

---

## 3. Copy Generation with Workers AI

```typescript
// workers/notification-personalizer/src/generate.ts
import { Ai } from "@cloudflare/ai";

interface CopyRequest {
  eventType: string;
  eventPayload: Record<string, unknown>;
  sentiment: "positive" | "neutral" | "frustrated";
  tone: "friendly" | "formal" | "minimal";
  language: string;
  defaultTitle: string;
  defaultBody: string;
}

interface NotificationCopy {
  title: string;
  body: string;
}

const SYSTEM_PROMPT = `You are a mobile push notification copywriter.
Write a SHORT notification title (max 40 chars) and body (max 90 chars).
Adapt the emotional tone to match the user's current mood.
Respond with ONLY valid JSON: {"title":"...","body":"..."}
Never include emojis unless tone is "friendly".`;

export async function generateCopy(
  req: CopyRequest,
  ai: Ai
): Promise<NotificationCopy> {
  const userPrompt = `
Event: ${req.eventType}
Payload summary: ${JSON.stringify(req.eventPayload).slice(0, 200)}
User sentiment: ${req.sentiment}
Preferred tone: ${req.tone}
Language: ${req.language}
Default title: ${req.defaultTitle}
Default body: ${req.defaultBody}

Rewrite the notification copy to match the user's mood and tone preference.
`.trim();

  try {
    const response = await ai.run("@cf/meta/llama-3.1-8b-instruct", {
      messages: [
        { role: "system", content: SYSTEM_PROMPT },
        { role: "user", content: userPrompt },
      ],
      max_tokens: 120,
      temperature: 0.4,
    });

    const text =
      typeof response === "string"
        ? response
        : (response as { response?: string }).response ?? "";

    // Extract JSON from response (model may wrap in backticks)
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) throw new Error("No JSON in response");
    const copy = JSON.parse(jsonMatch[0]) as NotificationCopy;

    // Hard length guards — truncate if model ignores the constraint
    return {
      title: copy.title.slice(0, 40),
      body: copy.body.slice(0, 90),
    };
  } catch (err) {
    console.error("[generateCopy] fallback to default:", err);
    return {
      title: req.defaultTitle.slice(0, 40),
      body: req.defaultBody.slice(0, 90),
    };
  }
}
```

---

## 4. Delivery to APNs and FCM

```typescript
// workers/notification-personalizer/src/deliver.ts
import type { Env, NotificationJob } from "./index";
import type { NotificationCopy } from "./generate";

export async function deliverIOS(
  job: NotificationJob,
  copy: NotificationCopy,
  env: Env
): Promise<void> {
  const payload = {
    aps: {
      alert: { title: copy.title, body: copy.body },
      sound: "default",
      badge: 1,
      "mutable-content": 0,
    },
    event: job.eventType,
    payload: job.eventPayload,
  };

  const res = await fetch(
    `https://api.push.apple.com/3/device/${job.deviceToken}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${env.APNS_TOKEN}`,
        "apns-push-type": "alert",
        "apns-priority": "10",
        "apns-topic": "com.example.app",
      },
      body: JSON.stringify(payload),
    }
  );

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`APNs ${res.status}: ${err}`);
  }
}

export async function deliverAndroid(
  job: NotificationJob,
  copy: NotificationCopy,
  env: Env
): Promise<void> {
  const payload = {
    message: {
      token: job.deviceToken,
      notification: {
        title: copy.title,
        body: copy.body,
      },
      data: {
        event: job.eventType,
        payload: JSON.stringify(job.eventPayload),
      },
    },
  };

  const res = await fetch(
    "https://fcm.googleapis.com/v1/projects/your-project/messages:send",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${env.FCM_KEY}`,
      },
      body: JSON.stringify(payload),
    }
  );

  if (!res.ok) {
    throw new Error(`FCM ${res.status}: ${await res.text()}`);
  }
}
```

---

## 5. Orchestrating the Full Pipeline

```typescript
// workers/notification-personalizer/src/process.ts
import type { Env, NotificationJob } from "./index";
import { fetchUserSignals, classifySentiment } from "./personalize";
import { generateCopy } from "./generate";
import { deliverIOS, deliverAndroid } from "./deliver";

export async function processJob(
  job: NotificationJob,
  env: Env
): Promise<void> {
  // 1. Fetch user signals (50ms max — KV read)
  const signals = await fetchUserSignals(job.userId, env);

  // 2. Classify sentiment from recent events
  const sentiment = await classifySentiment(signals.recentEvents, env.AI);

  // 3. Generate personalised copy
  const copy = await generateCopy({
    eventType: job.eventType,
    eventPayload: job.eventPayload,
    sentiment,
    tone: signals.preferredTone,
    language: signals.language,
    defaultTitle: job.defaultTitle,
    defaultBody: job.defaultBody,
  }, env.AI);

  // 4. Deliver
  if (job.platform === "ios") {
    await deliverIOS(job, copy, env);
  } else {
    await deliverAndroid(job, copy, env);
  }
}
```

---

## 6. Updating User Signals from the Mobile App

On the client, emit signal updates whenever a meaningful user action occurs:

```typescript
// React Native — src/hooks/useSignalTracker.ts
import { useCallback } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";

const SIGNALS_ENDPOINT = "https://api.example.com/signals";

export function useSignalTracker(userId: string) {
  const emitSignal = useCallback(
    async (type: string, label?: string) => {
      const signal = { type, label, ts: Date.now() };

      // Optimistic local append for offline resilience
      const raw = await AsyncStorage.getItem(`signals:${userId}`);
      const existing: typeof signal[] = raw ? JSON.parse(raw) : [];
      const updated = [...existing.slice(-49), signal];
      await AsyncStorage.setItem(`signals:${userId}`, JSON.stringify(updated));

      // Background flush to Worker
      fetch(`${SIGNALS_ENDPOINT}/${userId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(signal),
      }).catch(() => {/* swallow — local store is source of truth */});
    },
    [userId]
  );

  return { emitSignal };
}
```

```typescript
// Usage in a screen
const { emitSignal } = useSignalTracker(currentUser.id);

// Call on meaningful interactions
await emitSignal("order_placed", "purchased headphones");
await emitSignal("support_ticket_opened", "can't connect bluetooth");
```

---

## Anti-Patterns

- **Running inference inline on the notification send request path.** Inference on llama-3.1-8b takes 300–800ms. Always offload to a Queue — the triggering request returns 202 immediately.
- **Trusting model output lengths.** Language models regularly exceed constraints. Hard-truncate every generated string before delivering.
- **Using sentiment to suppress notifications.** Low-sentiment users need notifications most. Use sentiment to change _tone_, never as a gate.
- **Storing PII in event labels.** Signal labels feed the LLM prompt. Strip names, emails, and payment data before writing to KV.
- **One model for all event types.** Commerce events (order shipped) are factual; social events (friend joined) are emotional. Route to different prompt templates.

---

## Gotchas

- **Workers AI rate limits.** The `@cf/meta/llama-3.1-8b-instruct` model has per-account RPS limits. For a high-volume notification pipeline (> 1 000 rps) use the `@cf/meta/llama-3-8b-instruct-awq` quantised variant or cache generated copy per event template.
- **SST-2 sentiment model is binary.** It only classifies positive/negative. For the "frustrated" label, combine a low-positive score (< 0.4) with a recency check — if the last event was `support_ticket_opened` or `refund_requested`, override to "frustrated".
- **KV eventual consistency.** A user who updates their tone preference in app may not have the change reflected in the Worker for up to 60 seconds. This is acceptable for notification copy; use the default tone if the KV read returns null.
- **LLM hallucination of brand names.** In the system prompt, add: "Never invent product names, prices, or order numbers not present in the payload."
- **FCM OAuth tokens expire.** The `FCM_KEY` in the env should be a short-lived OAuth 2.0 access token refreshed via a Durable Object or a scheduled Worker running every 30 minutes.

---

## Verification

```bash
# Push a test job onto the queue
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/queues/$QUEUE_ID/messages" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{
      "body": {
        "userId": "usr_test_001",
        "platform": "ios",
        "deviceToken": "SIMULATOR_TOKEN",
        "eventType": "order_ready",
        "eventPayload": {"orderId": "ORD-123", "item": "Blue Hoodie"},
        "defaultTitle": "Your order is ready",
        "defaultBody": "Pick up your Blue Hoodie now"
      }
    }]
  }'

# Tail Worker logs to see sentiment + generated copy
wrangler tail notification-personalizer --format pretty
```

---

## Related

- `ios-push-notifications-apns-workers.md`
- `mobile-push-notifications-cloudflare-queues.md`
- `cloudflare-workers-ai-mobile-inference-edge.md`
- `mobile-push-delivery-reliability.md`
- `mobile-push-notifications-rich-interactive.md`

---

## Sources

- Cloudflare Workers AI — https://developers.cloudflare.com/workers-ai/
- Workers AI model catalog — https://developers.cloudflare.com/workers-ai/models/
- Cloudflare Queues — https://developers.cloudflare.com/queues/
- APNs HTTP/2 API — https://developer.apple.com/documentation/usernotifications/sending-notifications-using-the-apns-api
- FCM HTTP v1 API — https://firebase.google.com/docs/reference/fcm/rest/v1/projects.messages/send
