# Self-Harm Content Detection with Workers AI

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

example project posts occasionally depict or describe non-suicidal self-injury (NSSI) — images of cuts, posts describing self-harm methods, or communities forming around self-harm encouragement. These differ from acute crisis signals (handled separately) in that they may be chronic, community-reinforcing, and involve image content as well as text. The moderation team needs a dedicated pipeline that classifies both modalities and applies safe messaging rewrites before content reaches the feed.

## Context

Self-harm content on anonymous platforms follows patterns distinct from suicidal ideation: it is frequently chronic and communal rather than acute, and it often propagates through visual imagery rather than text alone. Cloudflare Workers AI provides both text classification via `@cf/meta/llama-3.1-8b-instruct` and image classification capabilities that can be chained in a single Worker. example project is subject to the UK Online Safety Act 2023 and the EU DSA, both of which explicitly require platforms to protect users from self-harm promotion content, with specific obligations around under-18 audiences. The pipeline must classify, rewrite where safe messaging guidelines apply, and create an immutable audit record in D1.

## Text-Modality Detection

Text posts are evaluated against a structured self-harm taxonomy that distinguishes passive ideation, method description, encouragement, and recovery content. Recovery and help-seeking content must never be suppressed.

```typescript
export interface Env {
  AI: Ai;
  DB: D1Database;
  R2: R2Bucket;
}

type SelfHarmCategory =
  | 'NONE'
  | 'RECOVERY'           // positive — do not suppress
  | 'PASSIVE_IDEATION'   // concern — add resources
  | 'METHOD_DESCRIPTION' // high — remove or blur
  | 'ENCOURAGEMENT';     // critical — immediate removal

interface TextClassification {
  category: SelfHarmCategory;
  confidence: number;
  safeMessagingViolation: boolean;
}

const SYSTEM_PROMPT = `You are a self-harm content safety classifier following safe messaging guidelines.
Classify the text into exactly one category:
- NONE: no self-harm content
- RECOVERY: help-seeking, recovery, anti-self-harm, support
- PASSIVE_IDEATION: vague distress or intrusive thoughts without methods
- METHOD_DESCRIPTION: describes specific self-harm methods, tools, or techniques
- ENCOURAGEMENT: actively encourages, glorifies, or challenges others to self-harm

Also flag safeMessagingViolation:true if the post includes method details, tools, or quantities.

Respond ONLY with JSON: {"category":"<CATEGORY>","confidence":0.0-1.0,"safeMessagingViolation":true|false}`;

async function classifyText(
  ai: Ai,
  text: string,
): Promise<TextClassification> {
  const result = await ai.run('@cf/meta/llama-3.1-8b-instruct', {
    messages: [
      { role: 'system', content: SYSTEM_PROMPT },
      { role: 'user', content: text },
    ],
    max_tokens: 120,
    temperature: 0,
  }) as { response: string };

  try {
    return JSON.parse(result.response.trim()) as TextClassification;
  } catch {
    return { category: 'NONE', confidence: 0, safeMessagingViolation: false };
  }
}
```

## Image-Modality Detection

Images are passed to `@cf/unum/uform-gen2-qwen-500m` with a targeted prompt. The model acts as a visual question-answering system; structured output indicates whether the image depicts self-harm injuries, instruments, or glorifying imagery. Images classified above threshold are sent to R2 under a quarantine prefix rather than the public content prefix.

```typescript
async function classifyImage(
  ai: Ai,
  imageBytes: Uint8Array,
): Promise<{ depicts: boolean; confidence: number }> {
  const vqaPrompt =
    'Does this image depict self-harm injuries, cuts, wounds, or implements commonly used for self-harm? Answer with JSON only: {"depicts":true|false,"confidence":0.0-1.0}';

  const result = await ai.run('@cf/unum/uform-gen2-qwen-500m', {
    image: [...imageBytes],
    prompt: vqaPrompt,
    max_tokens: 60,
  }) as { description: string };

  try {
    return JSON.parse(result.description.trim());
  } catch {
    return { depicts: false, confidence: 0 };
  }
}

async function quarantineImage(
  r2: R2Bucket,
  imageBytes: Uint8Array,
  postId: string,
  mimeType: string,
): Promise<string> {
  const key = `quarantine/self-harm/${postId}-${Date.now()}`;
  await r2.put(key, imageBytes, {
    httpMetadata: { contentType: mimeType },
    customMetadata: { postId, quarantinedAt: new Date().toISOString() },
  });
  return key;
}
```

## Orchestration Worker and D1 Audit Record

```typescript
interface IngestPayload {
  postId: string;
  sessionToken: string;
  text?: string;
  imageBase64?: string;
  imageMimeType?: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const payload = await request.json<IngestPayload>();
    const { postId, sessionToken, text, imageBase64, imageMimeType } = payload;

    let textResult: TextClassification | null = null;
    let imageDepicts = false;
    let imageConfidence = 0;
    let quarantineKey: string | null = null;

    // Run text and image classification in parallel where both are present
    const tasks: Promise<void>[] = [];

    if (text) {
      tasks.push(
        classifyText(env.AI, text).then((r) => { textResult = r; }),
      );
    }

    if (imageBase64 && imageMimeType) {
      const imageBytes = Uint8Array.from(atob(imageBase64), (c) => c.charCodeAt(0));
      tasks.push(
        classifyImage(env.AI, imageBytes).then(async (img) => {
          imageDepicts = img.depicts;
          imageConfidence = img.confidence;
          if (img.depicts && img.confidence > 0.7) {
            quarantineKey = await quarantineImage(
              env.R2,
              imageBytes,
              postId,
              imageMimeType,
            );
          }
        }),
      );
    }

    await Promise.all(tasks);

    // Determine final action
    const criticalText =
      textResult?.category === 'ENCOURAGEMENT' ||
      textResult?.category === 'METHOD_DESCRIPTION';
    const criticalImage = imageDepicts && imageConfidence > 0.7;
    const action = criticalText || criticalImage ? 'REMOVE' :
      textResult?.category === 'PASSIVE_IDEATION' ? 'ADD_RESOURCES' : 'ALLOW';

    // Audit record
    await env.DB.prepare(
      `INSERT INTO self_harm_audit
         (post_id, session_token, text_category, text_confidence, safe_msg_violation,
          image_depicts, image_confidence, quarantine_key, action, created_at)
       VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10)`,
    )
      .bind(
        postId, sessionToken,
        textResult?.category ?? null,
        textResult?.confidence ?? null,
        textResult?.safeMessagingViolation ? 1 : 0,
        imageDepicts ? 1 : 0,
        imageConfidence,
        quarantineKey,
        action,
        new Date().toISOString(),
      )
      .run();

    const RESOURCE_BANNER =
      'If you are struggling, please contact the Crisis Text Line (text HOME to 741741) or visit https://www.crisistextline.org';

    return Response.json({
      action,
      addResourceBanner: action === 'ADD_RESOURCES',
      resourceBanner: action === 'ADD_RESOURCES' ? RESOURCE_BANNER : undefined,
    });
  },
} satisfies ExportedHandler<Env>;
```

## D1 Schema

```sql
-- migration: 0007_self_harm_audit.sql
CREATE TABLE IF NOT EXISTS self_harm_audit (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id              TEXT NOT NULL,
  session_token        TEXT NOT NULL,
  text_category        TEXT,
  text_confidence      REAL,
  safe_msg_violation   INTEGER NOT NULL DEFAULT 0,
  image_depicts        INTEGER NOT NULL DEFAULT 0,
  image_confidence     REAL NOT NULL DEFAULT 0,
  quarantine_key       TEXT,
  action               TEXT NOT NULL CHECK(action IN ('ALLOW','ADD_RESOURCES','REMOVE')),
  created_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sh_action
  ON self_harm_audit(action, created_at DESC);
```

## Anti-patterns

- Suppressing `RECOVERY` category posts — this is a safe messaging violation and harms users seeking support.
- Using only keyword matching for self-harm detection; euphemisms and coded language (e.g., "butterfly project", "SH") require semantic understanding.
- Storing raw post text containing self-harm method descriptions in D1 indefinitely — retain audit metadata only and purge text after the moderation decision window.

## Gotchas

- The VQA model interprets the entire image; medical or educational diagrams of anatomy can trigger false positives — combine with an allow-list of verified educational account IDs before quarantining.
- `Uint8Array.from(atob(...))` fails on large base64 payloads in Workers due to the 128 MB memory limit; prefer streaming R2 uploads via `fetch` with a `ReadableStream` body for images above 1 MB.

## Verification

```bash
# Send a text-only test with METHOD_DESCRIPTION content (use synthetic test string)
curl -X POST https://example project-ingest.example.workers.dev/post \
  -H "Content-Type: application/json" \
  -d '{"postId":"p002","sessionToken":"s_xyz","text":"[SYNTHETIC TEST] method description here"}'

# Confirm audit record
wrangler d1 execute example project-db \
  --command "SELECT post_id, text_category, action, created_at FROM self_harm_audit ORDER BY created_at DESC LIMIT 10"

# List quarantined images
wrangler r2 object list example project-content --prefix "quarantine/self-harm/"
```

## Related

- `issues/crisis-intervention-detection-workers-ai.md`
- `issues/real-time-toxic-content-scoring-workers-ai.md`
- `issues/underage-user-detection-behavioral-signals.md`
- `issues/hash-based-duplicate-content-detection-r2.md`

## Sources

- https://developers.cloudflare.com/workers-ai/models/llama-3.1-8b-instruct/
- https://developers.cloudflare.com/r2/
- https://www.sprc.org/resources-programs/safe-messaging-guidelines/
- https://www.legislation.gov.uk/ukpga/2023/50/contents
