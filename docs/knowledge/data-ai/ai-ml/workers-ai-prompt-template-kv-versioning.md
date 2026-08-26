# Workers AI Prompt Template Versioning with KV Storage

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Prompt text is embedded in Worker source code. Improving a prompt requires a full
redeployment, making iteration slow and risky—a bad prompt change ships to 100 % of
traffic instantly. Teams operating multiple AI features accumulate dozens of hard-coded
prompt strings scattered across files, with no audit trail of what changed or why.
You need a system where prompts are versioned assets: editable without redeployment,
rollback-able in seconds, A/B-testable across traffic splits, and auditable via a
change log.

## Context

Cloudflare KV (Key–Value) is a globally replicated store with strong read-after-write
consistency within a Cloudflare data-centre and eventual global consistency (typically
< 60 s). Because Workers can read KV on every request, a prompt change written to KV
propagates to all Worker instances within one minute—far faster than a Worker
redeployment.

The pattern stores prompt templates in KV as JSON objects containing:
- The prompt text with `{{variable}}` placeholders.
- A semantic version tag.
- Metadata: author, description, created timestamp.

A thin `PromptStore` class handles reads with short `cacheTtl` (60 s for production,
0 for staging) so rollouts and rollbacks are near-instant.

## KV Namespace and Schema

```jsonc
// wrangler.jsonc
{
  "name": "prompt-worker",
  "compatibility_date": "2025-09-01",
  "ai": { "binding": "AI" },
  "kv_namespaces": [
    { "binding": "PROMPT_STORE",   "id": "your-kv-prod-id"    },
    { "binding": "PROMPT_AUDIT",   "id": "your-kv-audit-id"   }
  ]
}
```

```typescript
// src/prompt-types.ts
export interface PromptTemplate {
  version: string;           // e.g., "2.4.1"
  text: string;              // prompt text with {{variable}} placeholders
  model: string;             // recommended model, e.g. "@cf/meta/llama-3.1-8b-instruct"
  temperature: number;
  maxTokens: number;
  description: string;
  author: string;
  createdAt: number;         // Unix timestamp ms
}

export type PromptVariables = Record<string, string>;
```

## PromptStore: Read-with-Cache and Render

```typescript
// src/prompt-store.ts
import type { PromptTemplate, PromptVariables } from "./prompt-types";

export class PromptStore {
  private kv: KVNamespace;
  private cacheTtl: number;

  constructor(kv: KVNamespace, cacheTtl = 60) {
    this.kv = kv;
    this.cacheTtl = cacheTtl;
  }

  /** Fetch a template by logical key.  Returns null if not found. */
  async get(key: string): Promise<PromptTemplate | null> {
    return this.kv.get<PromptTemplate>(key, {
      type: "json",
      cacheTtl: this.cacheTtl,
    });
  }

  /** Fetch or throw. */
  async getOrThrow(key: string): Promise<PromptTemplate> {
    const t = await this.get(key);
    if (!t) throw new Error(`Prompt template not found: ${key}`);
    return t;
  }

  /**
   * Render a template by replacing {{variable}} placeholders.
   * Unknown placeholders are left intact for debugging.
   */
  render(template: PromptTemplate, vars: PromptVariables): string {
    return template.text.replace(
      /\{\{(\w+)\}\}/g,
      (match, key) => vars[key] ?? match,
    );
  }

  /**
   * Perform an inference call using the template's recommended settings.
   * `systemVars` fill {{}} tokens in the system role; `userMessage` is
   * appended as the user turn.
   */
  async runWithTemplate(
    ai: Ai,
    key: string,
    systemVars: PromptVariables,
    userMessage: string,
    overrides: Partial<{ model: string; temperature: number; maxTokens: number }> = {},
  ): Promise<{ response: string; templateVersion: string }> {
    const template = await this.getOrThrow(key);
    const systemText = this.render(template, systemVars);

    const result = await ai.run(
      overrides.model ?? template.model,
      {
        messages: [
          { role: "system", content: systemText },
          { role: "user",   content: userMessage },
        ],
        temperature: overrides.temperature ?? template.temperature,
        max_tokens:  overrides.maxTokens    ?? template.maxTokens,
      },
    );

    const response =
      typeof result === "object" && "response" in result
        ? (result as { response: string }).response
        : "";

    return { response, templateVersion: template.version };
  }
}
```

## CLI: Publishing and Rolling Back Templates

```typescript
// scripts/prompt-publish.ts  — runs in CI, not inside Workers
import { execSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import type { PromptTemplate } from "../src/prompt-types";

const [,, action, ...args] = process.argv;
const KV_BINDING = "PROMPT_STORE";

function publish(templatePath: string): void {
  const raw = fs.readFileSync(templatePath, "utf-8");
  const template: PromptTemplate = JSON.parse(raw);

  // Derive KV key from filename: e.g. "support-triage.json" → "support-triage"
  const key = path.basename(templatePath, ".json");

  // Write the new version
  execSync(
    `wrangler kv key put --binding ${KV_BINDING} "${key}" '${JSON.stringify(template)}'`,
    { stdio: "inherit" },
  );

  // Write an audit entry
  const auditKey = `audit:${key}:${Date.now()}`;
  execSync(
    `wrangler kv key put --binding PROMPT_AUDIT "${auditKey}" '${JSON.stringify({
      key,
      version: template.version,
      author:  template.author,
      action:  "publish",
      at:      Date.now(),
    })}'`,
    { stdio: "inherit" },
  );

  console.log(`Published ${key}@${template.version}`);
}

function rollback(key: string, targetVersion: string): void {
  // List audit entries to find the KV value for the target version
  const out = execSync(
    `wrangler kv key list --binding PROMPT_AUDIT --prefix "audit:${key}:"`,
    { encoding: "utf-8" },
  );
  const entries: { name: string }[] = JSON.parse(out);

  // Audit entries are newest-first; find the last publish of targetVersion
  for (const e of entries) {
    const audit = JSON.parse(
      execSync(
        `wrangler kv key get --binding PROMPT_AUDIT "${e.name}"`,
        { encoding: "utf-8" },
      ),
    );
    if (audit.version === targetVersion && audit.action === "publish") {
      console.log(`Rolled back ${key} to ${targetVersion} (sourced from audit trail)`);
      // In practice, maintain a versioned archive: prompt-store:key:version
      // and copy it back to the live key here.
      return;
    }
  }
  throw new Error(`Version ${targetVersion} not found in audit trail for ${key}`);
}

if (action === "publish") {
  publish(args[0]);
} else if (action === "rollback") {
  rollback(args[0], args[1]);
} else {
  console.error("Usage: prompt-publish publish <file.json> | rollback <key> <version>");
  process.exit(1);
}
```

## A/B Testing Prompt Variants

```typescript
// src/ab-prompt.ts
import { PromptStore } from "./prompt-store";

/**
 * Randomly assign a user to variant A or B based on a stable hash of their ID.
 * Returns the same variant for the same userId on every call.
 */
function assignVariant(userId: string, splitPercent = 50): "A" | "B" {
  let hash = 0;
  for (let i = 0; i < userId.length; i++) {
    hash = (hash * 31 + userId.charCodeAt(i)) >>> 0;
  }
  return (hash % 100) < splitPercent ? "A" : "B";
}

export async function runAbInference(
  ai: Ai,
  store: PromptStore,
  userId: string,
  userMessage: string,
): Promise<{ response: string; variant: "A" | "B"; templateVersion: string }> {
  const variant = assignVariant(userId);
  const templateKey = variant === "A" ? "support-triage-v2" : "support-triage-v2-b";

  const { response, templateVersion } = await store.runWithTemplate(
    ai,
    templateKey,
    { productName: "Acme Widget" },
    userMessage,
  );

  return { response, variant, templateVersion };
}
```

Log the `variant` and `templateVersion` with each response to a D1 table or AI Gateway
log field to calculate per-variant quality metrics offline.

## Versioned Archive Pattern

For true rollback, store each published version under a versioned key in addition to
the live key:

```bash
# On publish: write to both live and archive keys
wrangler kv key put --binding PROMPT_STORE "support-triage"         "$(cat support-triage.json)"
wrangler kv key put --binding PROMPT_STORE "support-triage@2.4.1"   "$(cat support-triage.json)"

# Rollback to 2.3.0:
wrangler kv key get --binding PROMPT_STORE "support-triage@2.3.0" \
  | wrangler kv key put --binding PROMPT_STORE "support-triage" -
```

Workers always read the live key (`support-triage`) with `cacheTtl: 60`. After a KV
write, the new prompt propagates globally within 60 s without any redeployment.

## Anti-patterns

- **Storing prompts only in environment variables**: env vars are baked into the Worker
  bundle at deploy time; changes require redeployment. KV enables live updates.
- **No `cacheTtl` on KV reads**: without caching, every AI request hits KV, adding
  10–50 ms of latency and driving up KV read costs at scale. Always use `cacheTtl`.
- **Overwriting the live key on every CI run without archiving**: makes rollback
  impossible. Always write a versioned archive key alongside the live key.
- **Embedding secrets or PII in prompt templates**: KV values are not encrypted at rest
  beyond Cloudflare's infrastructure encryption. Never store API keys or personal data
  in prompt templates.
- **Using KV for high-frequency per-user context**: KV is for shared templates, not
  per-user conversation history (which belongs in Durable Objects or D1).

## Gotchas

- **KV eventual consistency**: a KV write from a Wrangler CLI command or Worker may
  take up to 60 s to propagate to all Cloudflare edge locations. Set `cacheTtl` to
  match or exceed this window to avoid serving a mix of old and new templates during
  rollout.
- **KV `cacheTtl` minimum is 60 s**: values smaller than 60 are silently clamped to
  60. For staging environments where instant updates are needed, pass `cacheTtl: 0`
  to disable caching (KV reads hit the origin on every request).
- **`wrangler kv key put` value size limit**: KV values are limited to 25 MB. Prompts
  with extensive few-shot examples can approach this; split into multiple keys if needed.
- **JSON `parse` failures on corrupt KV values**: always wrap `kv.get<T>()` in
  try/catch and fall back to a hard-coded default prompt to prevent total service failure.

## Verification

```bash
# Publish a template
cat > /tmp/support-triage.json <<'EOF'
{
  "version": "2.4.1",
  "text": "You are a support agent for {{productName}}. Be concise and empathetic.",
  "model": "@cf/meta/llama-3.1-8b-instruct",
  "temperature": 0.3,
  "maxTokens": 256,
  "description": "Tier-1 support triage prompt",
  "author": "example.com",
  "createdAt": 1753228800000
}
EOF
wrangler kv key put --binding PROMPT_STORE "support-triage" "$(cat /tmp/support-triage.json)"

# Verify the live key is readable
wrangler kv key get --binding PROMPT_STORE "support-triage" | jq .version

# Test via the Worker
curl -s -X POST https://prompt-worker.example.workers.dev \
  -H "Content-Type: application/json" \
  -d '{"userId":"user-42","message":"My package is late"}' | jq '{variant,templateVersion,response}'

# Simulate rollback: overwrite live key with previous version
wrangler kv key put --binding PROMPT_STORE "support-triage" \
  "$(wrangler kv key get --binding PROMPT_STORE "support-triage@2.3.0")"
```

## Related

- `prompt-versioning.md`
- `prompt-engineering-fundamentals.md`
- `prompt-testing-evals.md`
- `llm-ab-testing.md`
- `workers-ai-durable-objects-stateful-sessions.md`
- `ai-feature-flag-patterns.md`
- `llm-shadow-deployment.md`

## Sources

- Cloudflare KV docs: https://developers.cloudflare.com/kv/
- KV read consistency and caching: https://developers.cloudflare.com/kv/reference/how-kv-works/
- `wrangler kv key put`: https://developers.cloudflare.com/workers/wrangler/commands/#kv-key-put
- Workers AI binding reference: https://developers.cloudflare.com/workers-ai/configuration/bindings/
