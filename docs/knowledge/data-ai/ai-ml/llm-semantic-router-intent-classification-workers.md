# LLM Semantic Router and Intent Classification in Workers

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
A single LLM endpoint receives queries covering wildly different intents — customer support, code generation, document search, SQL generation — each needing a different model, system prompt, and downstream tool. Routing based on keyword matching is brittle; a semantic router classifies intent from the query embedding and dispatches to the right handler before any expensive LLM call.

## Context
A semantic router stores a small set of labelled "route embeddings" in Vectorize (or in-memory for tiny route sets). Each incoming query is embedded, the nearest route is found by cosine similarity, and the request is forwarded to the matched handler. Workers AI provides the embedding model; the routing logic runs entirely at the edge with sub-10 ms classification latency. For ambiguous queries a confidence threshold gates fallback to a general-purpose handler.

## Route Definition and Seed Embedding

```typescript
// routes.ts
export interface Route {
  name: string;
  description: string;
  /** Representative example utterances for this intent */
  examples: string[];
  handler: string; // logical handler key
  model: string;   // LLM model to use for this route
  systemPrompt: string;
}

export const ROUTES: Route[] = [
  {
    name: 'sql_generation',
    description: 'Generate SQL queries from natural language',
    examples: [
      'Write a SQL query to find all users who signed up last month',
      'How do I select the top 10 products by revenue?',
      'Show me the SQL for a LEFT JOIN between orders and customers',
    ],
    handler: 'sql',
    model: '@cf/defog/sqlcoder-7b-2',
    systemPrompt: 'You are an expert SQL assistant. Generate correct SQL only.',
  },
  {
    name: 'code_generation',
    description: 'Write or explain code in any programming language',
    examples: [
      'Write a Python function to parse a CSV file',
      'Explain what this TypeScript generic does',
      'How do I implement a binary search in Rust?',
    ],
    handler: 'code',
    model: '@cf/meta/llama-3.1-8b-instruct',
    systemPrompt: 'You are an expert software engineer. Provide clean, working code with explanations.',
  },
  {
    name: 'document_qa',
    description: 'Answer questions from retrieved document context',
    examples: [
      'What does the refund policy say?',
      'Find the section about data retention in the privacy policy',
      'Summarise the key points from the uploaded report',
    ],
    handler: 'rag',
    model: '@cf/meta/llama-3.1-8b-instruct',
    systemPrompt: 'Answer only from the provided context. If unsure, say so.',
  },
  {
    name: 'customer_support',
    description: 'Handle customer service enquiries and complaints',
    examples: [
      'My order has not arrived after two weeks',
      'I need to cancel my subscription',
      'How do I reset my password?',
    ],
    handler: 'support',
    model: '@cf/meta/llama-3.1-8b-instruct',
    systemPrompt: 'You are a friendly customer support agent. Be empathetic and concise.',
  },
];
```

## Seed Script: Embed and Upsert Route Examples

```typescript
// seed-routes.ts  (run once via wrangler dev --test-scheduled or a one-shot Worker)
import type { VectorizeIndex, Ai } from '@cloudflare/workers-types';
import { ROUTES } from './routes';

interface Env {
  VECTORIZE: VectorizeIndex;
  AI: Ai;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    for (const route of ROUTES) {
      const emb = await env.AI.run('@cf/baai/bge-base-en-v1.5', {
        text: route.examples,
      });
      const vecs = (emb as { data: number[][] }).data.map((v, i) => ({
        id: `route::${route.name}::${i}`,
        values: v,
        metadata: {
          routeName: route.name,
          handler: route.handler,
          model: route.model,
          example: route.examples[i],
        },
      }));
      await env.VECTORIZE.upsert(vecs);
      console.log(`Seeded ${vecs.length} vectors for route "${route.name}"`);
    }
  },
} satisfies ExportedHandler<Env>;
```

## Router Worker: Classify and Dispatch

```typescript
// router.ts
import type { VectorizeIndex, Ai } from '@cloudflare/workers-types';
import { ROUTES, type Route } from './routes';

interface Env {
  VECTORIZE: VectorizeIndex;
  AI: Ai;
  // Handler service bindings (Workers-to-Workers via service bindings)
  SQL_HANDLER: Fetcher;
  CODE_HANDLER: Fetcher;
  RAG_HANDLER: Fetcher;
  SUPPORT_HANDLER: Fetcher;
}

interface RouterDecision {
  routeName: string;
  handler: string;
  model: string;
  confidence: number; // cosine similarity of top match
  fallback: boolean;
}

const CONFIDENCE_THRESHOLD = 0.55; // below this → fallback general handler
const FALLBACK_ROUTE: Pick<Route, 'name' | 'handler' | 'model' | 'systemPrompt'> = {
  name: 'general',
  handler: 'code', // reuse code handler as general fallback
  model: '@cf/meta/llama-3.1-8b-instruct',
  systemPrompt: 'You are a helpful assistant.',
};

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { query, history } = (await req.json()) as {
      query: string;
      history?: Array<{ role: string; content: string }>;
    };

    const decision = await classifyIntent(env, query);

    // Attach routing metadata to request and forward to handler
    const handlerReq = new Request(req.url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query,
        history: history ?? [],
        model: decision.model,
        routeName: decision.routeName,
        systemPrompt: getSystemPrompt(decision.routeName),
      }),
    });

    const handler = selectHandler(env, decision.handler);
    const response = await handler.fetch(handlerReq);

    // Surface routing decision in response headers for observability
    const headers = new Headers(response.headers);
    headers.set('x-route', decision.routeName);
    headers.set('x-route-confidence', decision.confidence.toFixed(3));
    headers.set('x-route-fallback', String(decision.fallback));

    return new Response(response.body, { status: response.status, headers });
  },
} satisfies ExportedHandler<Env>;

async function classifyIntent(env: Env, query: string): Promise<RouterDecision> {
  const embResp = await env.AI.run('@cf/baai/bge-base-en-v1.5', {
    text: [query],
  });
  const queryVec = (embResp as { data: number[][] }).data[0];

  const results = await env.VECTORIZE.query(queryVec, {
    topK: 3,
    returnMetadata: 'all',
  });

  const top = results.matches[0];
  if (!top || top.score < CONFIDENCE_THRESHOLD) {
    return {
      routeName: FALLBACK_ROUTE.name,
      handler: FALLBACK_ROUTE.handler,
      model: FALLBACK_ROUTE.model,
      confidence: top?.score ?? 0,
      fallback: true,
    };
  }

  const meta = top.metadata as {
    routeName: string;
    handler: string;
    model: string;
  };

  return {
    routeName: meta.routeName,
    handler: meta.handler,
    model: meta.model,
    confidence: top.score,
    fallback: false,
  };
}

function selectHandler(env: Env, handler: string): Fetcher {
  const map: Record<string, Fetcher> = {
    sql: env.SQL_HANDLER,
    code: env.CODE_HANDLER,
    rag: env.RAG_HANDLER,
    support: env.SUPPORT_HANDLER,
  };
  return map[handler] ?? env.CODE_HANDLER;
}

function getSystemPrompt(routeName: string): string {
  return ROUTES.find(r => r.name === routeName)?.systemPrompt
    ?? FALLBACK_ROUTE.systemPrompt;
}
```

## Confidence Calibration and Observability

```typescript
// analytics.ts — log routing decisions to Analytics Engine
interface Env {
  ANALYTICS: AnalyticsEngineDataset;
}

export function logRoutingDecision(
  env: Env,
  query: string,
  decision: {
    routeName: string;
    confidence: number;
    fallback: boolean;
    latencyMs: number;
  },
): void {
  env.ANALYTICS.writeDataPoint({
    blobs: [decision.routeName, query.slice(0, 128)],
    doubles: [decision.confidence, decision.latencyMs],
    indexes: [decision.fallback ? 'fallback' : 'routed'],
  });
}
```

## Route Management: Adding New Intents at Runtime

```typescript
// add-route.ts  (admin endpoint, protected by auth middleware)
export async function addRoute(
  env: Env,
  route: Pick<Route, 'name' | 'examples' | 'handler' | 'model' | 'systemPrompt'>,
): Promise<void> {
  const emb = await env.AI.run('@cf/baai/bge-base-en-v1.5', {
    text: route.examples,
  });
  const vecs = (emb as { data: number[][] }).data.map((v, i) => ({
    id: `route::${route.name}::${i}`,
    values: v,
    metadata: {
      routeName: route.name,
      handler: route.handler,
      model: route.model,
    },
  }));
  await env.VECTORIZE.upsert(vecs);
}
```

## Anti-patterns

- **Using keyword matching as the primary router** — "SELECT" in a query does not guarantee SQL intent; embed semantics, not surface tokens.
- **Setting the confidence threshold too low (< 0.4)** — misroutes queries to specialised handlers that then fail or hallucinate on out-of-domain input.
- **Seeding only one example utterance per route** — a single example produces a point in embedding space that is too narrow; use 3–10 diverse examples per intent.
- **Not exposing routing decisions in response headers or logs** — without observability you cannot detect systematic misroutes or tune the threshold.
- **Calling the embedding model and routing inline on every turn of a multi-turn conversation** — cache the route decision in the session KV after the first turn; subsequent turns in the same session need no re-classification.

## Gotchas

- Vectorize ANN search at `topK: 1` can be brittle near decision boundaries; retrieve `topK: 3` and check whether the top-3 all agree on the same `routeName` as a confidence signal.
- `@cf/baai/bge-base-en-v1.5` normalises embeddings to unit vectors; cosine similarity equals dot product — Vectorize default metric (`cosine`) is correct.
- Workers-to-Workers service bindings (`Fetcher`) are zero-latency RPC when both Workers are in the same account; they do not traverse the network.
- Route example utterances must cover the linguistic diversity of real queries — collect from production logs after initial deployment and retrain the route embeddings monthly.
- Adding new routes requires re-seeding only the new route's examples; existing vectors in Vectorize are unaffected.

## Verification

```bash
# 1. Seed routes (run once)
wrangler dev --test-scheduled  # triggers scheduled() seeder

# 2. Test SQL route
curl -X POST https://<router-worker>/chat \
  -H 'Content-Type: application/json' \
  -d '{"query":"Show me all orders placed in the last 7 days grouped by country"}'
# Expected headers: x-route: sql_generation, x-route-confidence: > 0.70

# 3. Test fallback
curl -X POST https://<router-worker>/chat \
  -d '{"query":"Can you help me with something?"}'
# Expected: x-route: general, x-route-fallback: true

# 4. Check Analytics Engine for routing distribution
wrangler analytics-engine query --dataset routing_decisions
```

## Related

- `llm-function-calling-tool-use-patterns.md`
- `ai-gateway-multi-provider-ab-testing.md`
- `llm-for-classification.md`
- `vectorize-multi-tenant-namespace-partitioning.md`
- `workers-ai-text-classification-moderation.md`

## Sources

- https://developers.cloudflare.com/vectorize/
- https://developers.cloudflare.com/workers/runtime-apis/service-bindings/
- https://github.com/aurelio-labs/semantic-router
