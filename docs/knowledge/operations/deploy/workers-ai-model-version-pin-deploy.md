# Workers AI Binding Model Version Pin Deploy

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

A Cloudflare Workers AI binding with an unversioned model identifier (e.g. `@cf/meta/llama-3.1-8b-instruct`) can silently receive a model update from Cloudflare that changes generation quality, token limits, or API surface. This causes regressions in production prompts, schema-breaking JSON outputs, and inconsistent evaluation results — with no deploy event to correlate the change to.

---

## Context

Workers AI exposes two categories of model identifiers:

- **Floating identifiers**: `@cf/meta/llama-3.1-8b-instruct` — always resolve to the latest version Cloudflare serves. Version changes are silent.
- **Pinned identifiers**: `@cf/meta/llama-3.1-8b-instruct@20241018` — resolve to a specific model snapshot. Version changes require an explicit update to the binding config and a new deploy.

Pinning model versions in `wrangler.toml` and asserting them in CI prevents silent regressions. The deploy artifact itself becomes the source of truth for which model version is in production.

---

## Pinning Model Versions in wrangler.toml

```toml
# wrangler.toml
name = "ai-worker"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[ai]
binding = "AI"

# Pinned model versions — update intentionally with a PR and deploy
[vars]
LLM_MODEL = "@cf/meta/llama-3.1-8b-instruct@20241018"
EMBEDDING_MODEL = "@cf/baai/bge-base-en-v1.5@20240101"
IMAGE_MODEL = "@cf/black-forest-labs/flux-1-schnell@20241101"

[env.staging]
[env.staging.vars]
LLM_MODEL = "@cf/meta/llama-3.1-8b-instruct@20241018"
EMBEDDING_MODEL = "@cf/baai/bge-base-en-v1.5@20240101"

[env.production]
[env.production.vars]
LLM_MODEL = "@cf/meta/llama-3.1-8b-instruct@20241018"
EMBEDDING_MODEL = "@cf/baai/bge-base-en-v1.5@20240101"
```

---

## Worker Code Consuming Pinned Model Vars

```typescript
// src/index.ts
export interface Env {
  AI: Ai;
  LLM_MODEL: string;
  EMBEDDING_MODEL: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { prompt } = await request.json() as { prompt: string };

    const response = await env.AI.run(
      env.LLM_MODEL as BaseAiTextGenerationModels,
      {
        messages: [
          { role: "system", content: "You are a helpful assistant." },
          { role: "user", content: prompt },
        ],
        max_tokens: 512,
      }
    );

    return Response.json({
      model: env.LLM_MODEL,
      response,
    });
  },
};
```

---

## CI Gate: Assert Model Version Pins

```typescript
// scripts/assert-model-pins.ts
import { readFileSync } from "fs";
import TOML from "@iarna/toml";

// Regex that matches a pinned identifier: @cf/org/name@date or @cf/org/name@version
const PINNED_PATTERN = /^@cf\/[^@]+@\d{8,}$/;

const REQUIRED_PINNED_VARS = [
  "LLM_MODEL",
  "EMBEDDING_MODEL",
];

function assertPins(config: any, envPath: string): string[] {
  const errors: string[] = [];
  const vars = config.vars ?? {};

  for (const varName of REQUIRED_PINNED_VARS) {
    const value = vars[varName];
    if (!value) {
      errors.push(`[${envPath}] missing var: ${varName}`);
      continue;
    }
    if (!PINNED_PATTERN.test(value)) {
      errors.push(
        `[${envPath}] ${varName}="${value}" is not a pinned model identifier. ` +
        `Expected format: @cf/org/model@YYYYMMDD`
      );
    }
  }

  return errors;
}

const raw = readFileSync("wrangler.toml", "utf-8");
const config = TOML.parse(raw) as any;

const errors: string[] = [
  ...assertPins(config, "root"),
  ...assertPins(config.env?.staging ?? {}, "env.staging"),
  ...assertPins(config.env?.production ?? {}, "env.production"),
];

if (errors.length > 0) {
  console.error("Model version pin check FAILED:");
  errors.forEach((e) => console.error(`  - ${e}`));
  process.exit(1);
}

console.log("All model version pins verified");
```

---

## Model Version Upgrade PR Automation

When Cloudflare releases a new snapshot, generate a PR to update the pin:

```typescript
// scripts/check-model-updates.ts
// Queries Workers AI catalog and compares to current pins in wrangler.toml

const CF_API_TOKEN = process.env.CLOUDFLARE_API_TOKEN!;
const CF_ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID!;

interface AiModel {
  name: string;
  versions?: Array<{ id: string; created_at: string }>;
}

async function listModels(): Promise<AiModel[]> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/ai/models/search`,
    { headers: { Authorization: `Bearer ${CF_API_TOKEN}` } }
  );
  const json = await res.json() as { result: AiModel[] };
  return json.result;
}

async function checkForUpdates(currentPins: Record<string, string>): Promise<void> {
  const models = await listModels();

  for (const [varName, pinned] of Object.entries(currentPins)) {
    // Extract base model name from pin: @cf/meta/llama-3.1-8b-instruct@20241018 → @cf/meta/llama-3.1-8b-instruct
    const baseName = pinned.replace(/@\d{8,}$/, "");
    const pinnedVersion = pinned.match(/@(\d{8,})$/)?.[1];

    const catalogModel = models.find((m) => m.name === baseName);
    if (!catalogModel?.versions?.length) continue;

    // Sort versions descending to get latest
    const latestVersion = catalogModel.versions
      .sort((a, b) => b.id.localeCompare(a.id))[0];

    if (latestVersion.id !== pinnedVersion) {
      console.log(
        `[${varName}] Update available: ${pinnedVersion} → ${latestVersion.id} (${baseName})`
      );
    } else {
      console.log(`[${varName}] Up to date: ${pinnedVersion}`);
    }
  }
}

checkForUpdates({
  LLM_MODEL: "@cf/meta/llama-3.1-8b-instruct@20241018",
  EMBEDDING_MODEL: "@cf/baai/bge-base-en-v1.5@20240101",
}).catch(console.error);
```

---

## Staging-to-Production Model Promotion Gate

```yaml
# .github/workflows/deploy-ai-worker.yml
name: Deploy AI Worker

on:
  push:
    branches: [main]

jobs:
  assert-pins:
    name: Assert Model Version Pins
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: npm ci
      - run: npx ts-node scripts/assert-model-pins.ts

  deploy-staging:
    needs: assert-pins
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: npm ci
      - name: Deploy to staging
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: npx wrangler deploy --env staging

      - name: Smoke-test AI response
        run: |
          RESULT=$(curl -s -X POST https://staging-ai-worker.example.com/ \
            -H "Content-Type: application/json" \
            -d '{"prompt": "Say OK"}')
          echo "$RESULT" | jq -e '.model | test("@\\d{8,}$")' \
            && echo "Model pin confirmed in response" \
            || (echo "Response missing pinned model"; exit 1)

  deploy-production:
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: npm ci
      - name: Deploy to production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: npx wrangler deploy --env production
```

---

## Anti-patterns

- **Using floating model identifiers in production** — `@cf/meta/llama-3.1-8b-instruct` with no version suffix can silently change behavior after a Cloudflare model update.
- **Hardcoding the model string in source code** — if the model identifier is in code rather than `wrangler.toml` vars, you must redeploy to update it, but there's no CI gate asserting its format.
- **Pinning different model versions in staging and production** — staging must run the exact same model version that will be promoted to production; divergence defeats validation.
- **Skipping the model update check in CI** — without a periodic check, outdated pins accumulate and important model improvements are missed.
- **Parsing model version strings at runtime** — the model pin validation should happen at deploy time in CI, not inside the worker on every request.

---

## Gotchas

- Not all Workers AI models support versioned identifiers; check the model catalog for each model's versioning support.
- The `@cf/org/model@version` syntax with a date version is Cloudflare-specific; version IDs are not semver.
- Pinned model versions may be retired by Cloudflare after a deprecation period; monitor the Workers AI changelog or automate version staleness checks.
- The `AI` binding in `wrangler.toml` under `[ai]` only declares the binding name; model selection happens at runtime via `env.AI.run(modelName, ...)`.
- Workers AI usage is metered per inference call; billing is not affected by pinned vs floating identifiers.

---

## Verification

```bash
# Confirm current model pin in wrangler.toml
grep -E "LLM_MODEL|EMBEDDING_MODEL" wrangler.toml

# Run pin assertion locally
npx ts-node scripts/assert-model-pins.ts

# Call deployed worker and verify model field in response
curl -s -X POST https://ai-worker.example.com/ \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Hello"}' | jq '{model, response}'
```

---

## Related

- `workers-binding-version-management.md`
- `env-binding-precedence.md`
- `wrangler-config-validation-pre-deploy-ci-hook.md`
- `wrangler-environments-promotion-pipeline.md`
- `environment-parity-staging-production.md`

---

## Sources

- https://developers.cloudflare.com/workers-ai/models/
- https://developers.cloudflare.com/workers-ai/configuration/bindings/
- https://developers.cloudflare.com/workers/wrangler/configuration/#ai
