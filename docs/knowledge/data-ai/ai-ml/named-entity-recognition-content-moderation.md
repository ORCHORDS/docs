# Named Entity Recognition for Content Moderation

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Your platform hosts user-generated content (UGC)—comments, bios, listings, reviews—that
may contain personally identifiable information (PII), references to real people's names,
brand names being misused, or geographic signals required for geo-restriction. You need to
extract these entities automatically so they can be:

- Redacted or masked before storage/display (PII).
- Flagged when a real person's name appears in defamatory context.
- Used to enforce content policies (competitor brand mentions, prohibited place names).
- Indexed for entity-based search and recommendation.

Traditional regex and dictionary-based NER fails on novel names, informal spelling, and
multilingual content. LLM-based NER handles these gracefully without maintaining word
lists.

## Context

Named Entity Recognition (NER) extracts structured entity objects from unstructured text.
Standard entity types:

| Type | Examples | Moderation use |
|---|---|---|
| `PERSON` | "John Smith", "Elon" | Defamation detection, PII |
| `ORG` | "Google", "NHS", "Acme Corp" | Brand policy, competitor mention |
| `LOCATION` | "Moscow", "Gaza Strip" | Geo-restriction, geopolitical content |
| `EMAIL` | "user@example.com" | PII, spam |
| `PHONE` | "+1-555-0100" | PII, spam |
| `URL` | "https://example.com" | Spam, phishing |
| `FINANCIAL` | "4111-1111-1111-1111" | Card numbers, PII |
| `DATE` | "March 15 2023" | Temporal context |

For content moderation, the high-value types are PERSON, ORG, LOCATION, EMAIL, PHONE,
URL, and FINANCIAL. These can be extracted and evaluated against policy rules independently
of the model that detects NSFW or toxic content.

NER runs synchronously (inline before content is stored) for short text (comments, bios)
and asynchronously (via Queue) for long-form content.

## LLM-Based NER with Structured Output

```typescript
interface Entity {
  text: string;        // Exact substring from the input
  type: EntityType;
  start: number;       // Character offset (optional, for highlighting)
  sensitivity: "public" | "pii" | "restricted";
}

type EntityType = "PERSON" | "ORG" | "LOCATION" | "EMAIL" | "PHONE" | "URL" | "FINANCIAL" | "DATE";

interface NERResult {
  entities: Entity[];
  has_pii: boolean;
  has_restricted: boolean;
}

async function extractEntities(
  ai: Ai,
  text: string
): Promise<NERResult> {
  const systemPrompt = `
You are a Named Entity Recognition (NER) system. Extract entities from the given text.

Entity types to extract:
- PERSON: full names, first names when clearly a person reference
- ORG: company names, organisations, institutions, brands
- LOCATION: countries, cities, addresses, geographic regions
- EMAIL: email addresses
- PHONE: phone numbers in any format
- URL: web URLs and domain names
- FINANCIAL: credit card numbers, bank account numbers, IBAN
- DATE: specific dates and date ranges

For each entity return:
- text: the exact substring from the input
- type: one of the types above
- sensitivity: "pii" if it could identify an individual (PERSON+location, EMAIL, PHONE, FINANCIAL), "restricted" if geopolitically sensitive or banned entity, otherwise "public"

Return ONLY a JSON object with this schema:
{
  "entities": [{"text":"...","type":"...","sensitivity":"..."}],
  "has_pii": <true|false>,
  "has_restricted": <true|false>
}

If no entities found, return {"entities":[],"has_pii":false,"has_restricted":false}.
`.trim();

  const response = await ai.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: `Extract entities from:\n\n${text.slice(0, 2000)}` },
    ],
    response_format: { type: "json_object" },
    max_tokens: 1024,
    temperature: 0.0,
  });

  try {
    const parsed = JSON.parse((response as { response: string }).response) as NERResult;
    // Ensure has_pii is computed from entities if not set
    if (typeof parsed.has_pii !== "boolean") {
      parsed.has_pii = parsed.entities.some((e) => e.sensitivity === "pii");
    }
    if (typeof parsed.has_restricted !== "boolean") {
      parsed.has_restricted = parsed.entities.some((e) => e.sensitivity === "restricted");
    }
    return parsed;
  } catch {
    return { entities: [], has_pii: false, has_restricted: false };
  }
}
```

## PII Redaction Pipeline

Once entities are extracted, redact PII types before storage:

```typescript
const PII_TYPES = new Set<EntityType>(["PERSON", "EMAIL", "PHONE", "FINANCIAL"]);

function redactPii(text: string, entities: Entity[]): string {
  // Sort entities by position (requires character offsets)
  // For simple replacement without offsets, use exact string replacement
  let redacted = text;

  for (const entity of entities) {
    if (!PII_TYPES.has(entity.type)) continue;

    const placeholder = `[${entity.type}]`;
    // Replace all occurrences of this entity text
    redacted = redacted.split(entity.text).join(placeholder);
  }

  return redacted;
}

// Usage
const ner = await extractEntities(env.AI, userComment);
const safeText = redactPii(userComment, ner.entities);

if (ner.has_pii) {
  // Log PII detection event
  await env.DB.prepare(
    "INSERT INTO moderation_events (content_id, event_type, metadata) VALUES (?, ?, ?)"
  )
    .bind(contentId, "pii_detected", JSON.stringify({ entity_types: ner.entities.map((e) => e.type) }))
    .run();
}
```

## Policy Rule Enforcement

Apply policy rules against extracted entities after NER:

```typescript
interface PolicyRule {
  entity_type: EntityType;
  pattern?: RegExp;           // Optional: further match entity text
  action: "block" | "flag" | "redact";
  reason: string;
}

const POLICY_RULES: PolicyRule[] = [
  { entity_type: "FINANCIAL", action: "block", reason: "card_number_detected" },
  { entity_type: "EMAIL",     action: "redact", reason: "email_in_ugc" },
  { entity_type: "PHONE",     action: "redact", reason: "phone_in_ugc" },
  { entity_type: "URL",
    pattern: /\.(ru|cn|kp)\//i,
    action: "flag",
    reason: "restricted_tld" },
];

interface ModerationDecision {
  action: "allow" | "block" | "flag" | "redact";
  reasons: string[];
  entities: Entity[];
}

function applyPolicies(ner: NERResult): ModerationDecision {
  const triggered: PolicyRule[] = [];

  for (const entity of ner.entities) {
    for (const rule of POLICY_RULES) {
      if (rule.entity_type !== entity.type) continue;
      if (rule.pattern && !rule.pattern.test(entity.text)) continue;
      triggered.push(rule);
    }
  }

  const actions = triggered.map((r) => r.action);
  const finalAction = actions.includes("block")
    ? "block"
    : actions.includes("flag")
    ? "flag"
    : actions.includes("redact")
    ? "redact"
    : "allow";

  return {
    action: finalAction,
    reasons: [...new Set(triggered.map((r) => r.reason))],
    entities: ner.entities,
  };
}
```

## Person Name Policy: Defamation Risk Detection

When a PERSON entity appears alongside negative sentiment, flag for human review:

```typescript
async function checkDefamationRisk(
  ai: Ai,
  text: string,
  personEntities: Entity[]
): Promise<{ risk: boolean; explanation: string }> {
  if (personEntities.length === 0) return { risk: false, explanation: "" };

  const names = personEntities.map((e) => `"${e.text}"`).join(", ");
  const prompt =
    `Text: "${text.slice(0, 800)}"\n\n` +
    `The text mentions these people: ${names}.\n` +
    `Does this text make false factual claims, accusations, or defamatory statements about any of them?\n` +
    `Reply with JSON: {"risk":true|false,"explanation":"<brief reason or empty string>"}`;

  const response = await ai.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [{ role: "user", content: prompt }],
    response_format: { type: "json_object" },
    max_tokens: 128,
    temperature: 0.0,
  });

  try {
    return JSON.parse((response as { response: string }).response);
  } catch {
    return { risk: false, explanation: "" };
  }
}
```

## Storing Entities for Entity-Based Search

Materialise extracted entities into a junction table for SQL-level filtering:

```sql
CREATE TABLE content_entities (
  content_id TEXT NOT NULL,
  entity_text TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  sensitivity TEXT NOT NULL,
  created_at INTEGER DEFAULT (unixepoch())
);

CREATE INDEX idx_content_entities_type ON content_entities(entity_type, entity_text);
CREATE INDEX idx_content_entities_content ON content_entities(content_id);
```

```typescript
async function storeEntities(
  db: D1Database,
  contentId: string,
  entities: Entity[]
): Promise<void> {
  const stmt = db.prepare(
    "INSERT OR IGNORE INTO content_entities (content_id, entity_text, entity_type, sensitivity) VALUES (?, ?, ?, ?)"
  );
  const batch = entities.map((e) =>
    stmt.bind(contentId, e.text, e.type, e.sensitivity)
  );
  if (batch.length > 0) await db.batch(batch);
}
```

## Anti-patterns

- **Running NER on every read.** Extract entities once on write and store. NER on read
  path will kill latency.
- **Blocking content solely based on NER.** NER identifies entities; it does not determine
  context. "John Smith committed perjury" may be factual journalism, not defamation. Flag
  for review rather than auto-blocking PERSON mentions.
- **Exact string replacement for redaction.** Case variations and Unicode normalisation
  differences mean "john@example.com" and "John@Example.com" may not be caught by naive
  `split().join()`. Normalize text before replacement or use case-insensitive regex.
- **Treating all URLs as harmful.** URL extraction is valuable for spam detection, but
  internal links and trusted domains should be allowlisted.
- **Using NER results as definitive truth.** LLMs occasionally hallucinate entity
  boundaries or misclassify entity types. For high-stakes decisions (legal holds,
  card number detection) supplement with regex pattern matching.
- **Logging full entity text for FINANCIAL types.** Do not store raw card numbers even
  in moderation logs. Store a hash or truncated form only.

## Gotchas

- `response_format: { type: "json_object" }` forces valid JSON but not schema compliance.
  The model may return `"entities": null` rather than `[]`; always guard with `?? []`.
- LLaMA-3.1-8b has a 4096-token context window. A 2000-character text plus system prompt
  typically fits within ~1200 tokens. Chunk longer content before extracting entities.
- Entity boundaries in the LLM output may not exactly match the input substring. Use fuzzy
  string matching (or the model's character offsets if provided) for accurate highlighting.
- NER is sensitive to prompt wording. "Extract entities" yields different results than
  "Find all people, organisations and locations." Test both phrasings on your data.
- Multilingual NER requires an instruction-tuned model with multilingual training data.
  LLaMA 3.1 8B handles English and major European languages well; for Arabic, Japanese,
  or Chinese NER, consider a dedicated multilingual model or pass `language` context.
- The `temperature=0.0` setting makes NER outputs deterministic but also removes the
  model's ability to express uncertainty. For ambiguous entities, a low non-zero
  temperature (0.1–0.2) with multiple samples and majority voting improves recall.

## Verification

```bash
# Test NER endpoint with PII-containing comment
curl -X POST https://api.example.com/moderate/ner \
  -H "Content-Type: application/json" \
  -d '{"text":"Hi, I am Jane Doe, reach me at jane.doe@example.com or +1 555-0123."}'

# Expected response structure
{
  "entities": [
    {"text":"Jane Doe","type":"PERSON","sensitivity":"pii"},
    {"text":"jane.doe@example.com","type":"EMAIL","sensitivity":"pii"},
    {"text":"+1 555-0123","type":"PHONE","sensitivity":"pii"}
  ],
  "has_pii": true,
  "has_restricted": false
}

# Verify redacted version was stored
curl https://api.example.com/content/test-id | jq .safe_content
# Expected: "Hi, I am [PERSON], reach me at [EMAIL] or [PHONE]."

# Test D1 entity index
wrangler d1 execute my-db --command \
  "SELECT content_id, entity_text FROM content_entities WHERE entity_type='EMAIL' LIMIT 5;"
```

## Related

- `pii-detection-redaction.md` — broader PII detection and data minimization patterns
- `ai-content-moderation-pipeline.md` — full moderation pipeline with multiple signals
- `llm-for-extraction.md` — general structured extraction with LLMs
- `llm-structured-output-json-mode.md` — enforcing JSON schema from LLM responses
- `ai-safety-guardrails-implementation.md` — combining NER with safety classifiers

## Sources

- Cloudflare Workers AI Models: https://developers.cloudflare.com/workers-ai/models/
- CoNLL-2003 NER benchmark: https://paperswithcode.com/dataset/conll-2003
- GLiNER universal NER paper: https://arxiv.org/abs/2311.08526
- GDPR Article 4 — definition of personal data: https://gdpr-info.eu/art-4-gdpr/
- NIST SP 800-122 — Guide to Protecting PII: https://csrc.nist.gov/publications/detail/sp/800-122/final
