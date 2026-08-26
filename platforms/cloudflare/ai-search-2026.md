# cloudflare-ai-search-2026

- **Issue**: AI Search is the new name for AutoRAG, and it has gone from "managed RAG" to "managed retrieval with hybrid search, relevance boosting, public endpoints, MCP, and Vercel/LangChain/Cloudflare Agents SDK integrations." The pre-2026 patterns miss most of this.
- **Date**: 2026-08-09
- **Repo**: example-org/example-repo
- **Author**: kb-batch-2
- **Status**: Active; supplements `documentation/categories/patterns/rag-architecture-2026.md`.

## Symptom

- You wired up AutoRAG to a single R2 bucket. You want a single endpoint that fans out across multiple instances (multi-tenant, per-agent, per-project).
- Your retrieval is vector-only and you want BM25 hybrid search with a configurable fusion method.
- You want to boost by recency or priority, and surface custom metadata in the search response.
- You want to expose the search endpoint to an MCP client without building an auth layer.
- You want to drive queries from Vercel AI SDK, LangChain, or Cloudflare Agents SDK without hand-rolling REST calls.

## Root cause (the 2026 capability set)

AI Search is the retrieval layer of the agent platform. It is not a Vectorize wrapper; it is a managed retrieval product with its own infrastructure, MIME support, and integrations. Migration from AutoRAG to AI Search is automatic (June 3, 2026 for pre-April-16 instances).

### What you can do today that you couldn't in 2025

1. **Hybrid search** combining vector (semantic) and BM25 (keyword) in one query, with a configurable fusion method per instance.
2. **Relevance boosting** on up to 3 metadata fields per instance, overrideable per request.
3. **Custom metadata filtering** — up to 5 custom fields per instance (`text`, `number`, `boolean`).
4. **Built-in storage, built-in vector index, built-in web crawling** — all migrated to managed infrastructure; no separate R2 bucket for crawling.
5. **MIME expansion** — `.gif`, `.bmp`, `.mdoc`, `.sql`, `.log.gz` now indexed.
6. **Namespace-level Wrangler commands** — `wrangler ai-search create / list / get / update / delete / search / stats`, with `--namespace` and `--json` flags.
7. **Multi-instance search via a namespace** — one `/search` call fans out across the instances you choose; results merged and ranked.
8. **Public endpoints** with custom domain, Cloudflare Access, and a `/mcp` path for MCP clients.
9. **Similarity cache freshness controls** — `cache_ttl` from 10 minutes to 6 days; default is now 48 hours (down from 30 days).
10. **Path filtering** for website and R2 data sources (include/exclude rules).
11. **CSS content selectors** for website sources — pick the parts of a page to index.
12. **Framework SDKs** — Cloudflare Agents SDK, Vercel AI SDK, LangChain (`langchain-cloudflare` on PyPI).
13. **AI Search binding** in Workers — `env.AI_SEARCH.create({ id: "tenant-a" })` and `env.AI_SEARCH.search(...)`.

### Quotas (during open beta)

- Up to **10 AI Search instances** per account
- Up to **100,000 files per instance**
- Free to enable during the open beta; Workers AI and AI Gateway are billed separately

## Patterns

### Per-tenant instance (multi-tenant SaaS)

```ts
export interface Env { AI_SEARCH: AiSearchNamespace; }

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const tenant = await getTenant(request);
    const instance = await env.AI_SEARCH.create({ id: `tenant-${tenant.id}` });
    const results = await instance.search({
      query: await request.text(),
      max_results: 10,
    });
    return Response.json(results);
  },
};
```

### Hybrid search with relevance boosting

```ts
const instance = await env.AI_SEARCH.get("docs-prod");
const results = await instance.search({
  query: "incident response runbook",
  hybrid: { enabled: true, keyword_match: "any", fusion: "rrf" },
  boost: [{ field: "timestamp", weight: 1.5 }, { field: "priority", weight: 2.0 }],
  filter: { category: "runbook" },
});
```

### MCP endpoint

```json
// claude_desktop_config.json
{ "mcpServers": { "ai-search": { "url": "https://<PUBLIC_ID>.search.ai.cloudflare.com/mcp" } } }
```

Behind Cloudflare Access, agents authenticate with a service token; humans sign in via the IdP.

### Pre-built web component

```ts
import "@cloudflare/ai-search-snippet";
export default function App() {
  return <search-bar-snippet apiUrl="https://<PUBLIC_ID>.search.ai.cloudflare.com/" />;
}
```

### LangChain retriever

```py
from langchain_cloudflare import CloudflareAISearchRetriever
retriever = CloudflareAISearchRetriever(instance_id="docs-prod")
docs = retriever.invoke("how does AI Search handle uploads?")
```

## Verification

- **Hit rate** on the similarity cache; track `cache_ttl` vs hit ratio. If your data updates daily, default 48-hour cache is too long; set to 24 hours or less.
- **Hybrid vs vector-only A/B** on a held-out query set; check whether BM25 lifts recall on the long tail of rare keywords.
- **Per-instance cost** (Workers AI + AI Gateway charges); if one tenant dominates, confirm the per-tenant instance is fair.
- **Migration status** (for pre-2026-04-16 instances): completed by 2026-06-03 with no downtime. Check that any old R2 bucket created for crawling is now unused and deletable.

## Gotchas

- **Migration is automatic on 2026-06-03** for pre-April-16 instances. Old `/autorag/rags/` endpoints still work but are deprecated; new endpoints are `/ai-search/...`.
- **`cache_ttl` default dropped from 30 days to 48 hours.** If you depended on long caching, re-validate behavior.
- **10-instance, 100K-file quotas are hard limits during open beta.** Plan for them.
- **Custom metadata: max 5 fields per instance, max 3 boost fields.** Pick the highest-signal fields only.
- **Per-tenant instances mean per-tenant cost.** For SaaS with many small tenants, vectorize-2026 + a shared instance may be cheaper.
- **Similarity cache and RAG are not free.** Always include `cache_ttl` and `max_results`; never rely on defaults for production.
- **CSS selectors for websites** require parse-options setup; the `discover` parse type starts from the source URL and follows links.
- **Cloudflare-AutoRAG user-agent was renamed to Cloudflare-AI-Search.** `robots.txt` allows both for backward compatibility.

## Related

- `documentation/categories/cloudflare/vectorize-2026.md` — the raw vector store
- `documentation/categories/patterns/rag-architecture-2026.md` — RAG topology
- `documentation/categories/patterns/multi-agent-orchestration.md` — agents calling AI Search as a tool
- `documentation/categories/patterns/mcp-server-patterns.md` — the MCP integration pattern

## Source URLs (verified 2026-08-09)

- Cloudflare AI Search product page — https://www.cloudflare.com/products/ai-search/
- AI Search release notes — https://developers.cloudflare.com/ai-search/platform/release-note/
- AI Search changelog — https://developers.cloudflare.com/changelog/product/ai-search/
- "AI Search now has hybrid search and relevance boosting" (2026-04-16) — https://developers.cloudflare.com/changelog/post/2026-04-16-hybrid-search-and-relevance-boosting/
- "Introducing AutoRAG" — https://blog.cloudflare.com/introducing-autorag-on-cloudflare/
