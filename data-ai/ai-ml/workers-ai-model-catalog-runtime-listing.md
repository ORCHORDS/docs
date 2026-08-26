# Workers AI Model Catalog Runtime Listing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to programmatically discover which AI models are available in your Cloudflare account at
runtime — to build a model-selection UI, enforce an allowlist, check whether a newly released model
is available before routing to it, or sync your model registry nightly without manually reading the
documentation page.

## Context

Cloudflare exposes the Workers AI model catalog through the REST API at
`GET /accounts/{account_id}/ai/models/search`. The endpoint returns paginated model objects with
metadata: model ID, task type (text-generation, text-embeddings, image-classification, etc.),
description, capabilities, context window length, and pricing tier. This is distinct from the
`env.AI.run()` binding — you cannot call the binding itself to list models; listing requires an
out-of-band API call with an API token.

Typical patterns:
- A Worker that proxies model selection to end-users fetches the catalog from KV on startup
  (warmed by a Cron Trigger nightly).
- A CI script validates that every model referenced in code is still in the live catalog before
  deploying.
- An admin dashboard renders live capability badges (supports `tools`, `stream`, `lora`).

## Fetching the Catalog

```typescript
// src/modelCatalog.ts

export interface WorkersAiModel {
  id: string;          // e.g. "@cf/meta/llama-3.1-8b-instruct"
  name: string;
  description: string;
  task: {
    id: string;        // e.g. "text-generation"
    name: string;
    description: string;
  };
  tags: string[];      // e.g. ["llama", "meta", "text-generation"]
  properties: Array<{
    property_id: string;   // e.g. "context_window", "lora", "function_calling"
    value: string;
  }>;
}

interface ModelSearchResponse {
  result: WorkersAiModel[];
  result_info: { count: number; page: number; per_page: number; total_count: number };
  success: boolean;
  errors: unknown[];
}

export async function fetchAllModels(
  accountId: string,
  apiToken: string,
  taskFilter?: string   // e.g. "text-generation"
): Promise<WorkersAiModel[]> {
  const all: WorkersAiModel[] = [];
  let page = 1;
  const perPage = 100;

  while (true) {
    const params = new URLSearchParams({
      page: String(page),
      per_page: String(perPage),
      ...(taskFilter ? { search: taskFilter } : {}),
    });

    const res = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${accountId}/ai/models/search?${params}`,
      { headers: { Authorization: `Bearer ${apiToken}` } }
    );

    if (!res.ok) throw new Error(`Model catalog fetch failed: ${res.status}`);

    const data: ModelSearchResponse = await res.json();
    all.push(...data.result);

    const { page: p, per_page: pp, total_count: total } = data.result_info;
    if (p * pp >= total) break;
    page++;
  }

  return all;
}
```

## Caching the Catalog in KV

The catalog rarely changes more than once a day. Cache it in KV and refresh via Cron Trigger.

```typescript
// src/catalogCache.ts
import { fetchAllModels, WorkersAiModel } from "./modelCatalog";

const CATALOG_KV_KEY = "workers_ai:model_catalog";
const CATALOG_TTL_SECONDS = 86_400; // 24 hours

export async function getCatalogFromKv(
  kv: KVNamespace
): Promise<WorkersAiModel[] | null> {
  return kv.get<WorkersAiModel[]>(CATALOG_KV_KEY, "json");
}

export async function refreshCatalogInKv(
  kv: KVNamespace,
  accountId: string,
  apiToken: string
): Promise<WorkersAiModel[]> {
  const models = await fetchAllModels(accountId, apiToken);
  await kv.put(CATALOG_KV_KEY, JSON.stringify(models), {
    expirationTtl: CATALOG_TTL_SECONDS,
  });
  return models;
}

// In wrangler.toml, attach a Cron Trigger:
// [[triggers.crons]]
// crons = ["0 3 * * *"]   # 03:00 UTC daily

// src/worker.ts (scheduled handler)
export const scheduled: ExportedHandlerScheduledHandler<Env> = async (
  _event,
  env
) => {
  await refreshCatalogInKv(env.MODEL_CATALOG_KV, env.CF_ACCOUNT_ID, env.CF_API_TOKEN);
};
```

## Querying Capabilities at Runtime

Parse the `properties` array to find models that support specific capabilities before routing.

```typescript
// src/capabilities.ts
import { WorkersAiModel } from "./modelCatalog";

export function getProperty(model: WorkersAiModel, key: string): string | undefined {
  return model.properties.find((p) => p.property_id === key)?.value;
}

export function supportsStreaming(model: WorkersAiModel): boolean {
  return getProperty(model, "streaming") === "true";
}

export function supportsFunctionCalling(model: WorkersAiModel): boolean {
  return getProperty(model, "function_calling") === "true";
}

export function supportsLora(model: WorkersAiModel): boolean {
  return getProperty(model, "lora") === "true";
}

export function getContextWindow(model: WorkersAiModel): number {
  return parseInt(getProperty(model, "context_window") ?? "4096", 10);
}

/** Return the best model for a given task that fits within a token budget. */
export function selectModel(
  catalog: WorkersAiModel[],
  task: string,
  requiredContextTokens: number,
  mustSupportTools: boolean
): WorkersAiModel | undefined {
  return catalog
    .filter(
      (m) =>
        m.task.id === task &&
        getContextWindow(m) >= requiredContextTokens &&
        (!mustSupportTools || supportsFunctionCalling(m))
    )
    .sort((a, b) => getContextWindow(a) - getContextWindow(b)) // prefer smallest that fits
    .at(0);
}
```

## CI Validation Script

Verify that every model referenced in source code is present in the live catalog before deploying.

```typescript
// scripts/validate-models.ts  (ts-node scripts/validate-models.ts)
import { fetchAllModels } from "../src/modelCatalog";

// Hard-coded model IDs used in the project.
const REQUIRED_MODELS = [
  "@cf/meta/llama-3.1-8b-instruct",
  "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
  "@cf/baai/bge-large-en-v1.5",
];

async function main() {
  const accountId = process.env.CF_ACCOUNT_ID!;
  const apiToken = process.env.CF_API_TOKEN!;

  const catalog = await fetchAllModels(accountId, apiToken);
  const catalogIds = new Set(catalog.map((m) => m.id));

  const missing = REQUIRED_MODELS.filter((id) => !catalogIds.has(id));

  if (missing.length > 0) {
    console.error("Missing models in Workers AI catalog:", missing);
    process.exit(1);
  }
  console.log(`All ${REQUIRED_MODELS.length} required models confirmed available.`);
}

main().catch(console.error);
```

## Anti-patterns

- **Calling the catalog API on every inference request** — the catalog changes infrequently; one
  uncached call per request adds 100–200 ms latency. Always cache in KV.
- **Filtering by model name string prefix** — model IDs contain author and version segments that
  change (`llama-3.1` vs `llama-3.3`). Use the `task.id` field plus capability properties instead.
- **Hardcoding the full model list** — when Cloudflare deprecates or renames a model the worker
  breaks silently. Use runtime validation to catch removals before production.
- **Ignoring pagination** — the catalog has well over 100 models across all task types.
  Fetching only page 1 (`per_page=50`) misses embedding and image generation models.

## Gotchas

- The `search` query parameter on the catalog endpoint performs a fuzzy text match against model
  name and description, not a strict `task.id` filter. Always post-filter the results.
- Some models appear in the catalog but are in beta and may not be available in all regions or
  plan tiers. A `400 model not found` from `ai.run()` does not mean the catalog is wrong — it may
  mean the model is not yet enabled on your account.
- The `result_info.total_count` field counts across all pages. If you filter by `search`, the
  total count still reflects the unfiltered set on some API versions; do not rely on it for
  filtered pagination.
- API token scope: the token needs `Workers AI:Read` permission; the full `AI Gateway:Edit` scope
  is not required.

## Verification

```bash
# Fetch first page of text-generation models and list their IDs:
curl -s \
  -H "Authorization: Bearer $CF_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/ai/models/search?search=text-generation&per_page=20" \
  | jq '.result[].id'

# Check a specific model's properties (context window, function_calling):
curl -s \
  -H "Authorization: Bearer $CF_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/ai/models/search?search=llama-3.1-8b-instruct" \
  | jq '.result[0].properties'
```

## Related

- `workers-ai-model-benchmarking-latency-profiling.md` — measuring actual latency after model selection
- `workers-ai-edge-vs-cloud-inference-decision-tree.md` — routing criteria beyond catalog capabilities
- `workers-ai-lora-adapter-management.md` — per-model LoRA adapters after capability check
- `ai-model-selection-workers-ai-inference.md` — qualitative selection guidance

## Sources

- Cloudflare Workers AI model list REST API: https://developers.cloudflare.com/api/operations/workers-ai-get-models
- Workers AI models page: https://developers.cloudflare.com/workers-ai/models/
- Cloudflare API token permissions: https://developers.cloudflare.com/fundamentals/api/reference/permissions/
