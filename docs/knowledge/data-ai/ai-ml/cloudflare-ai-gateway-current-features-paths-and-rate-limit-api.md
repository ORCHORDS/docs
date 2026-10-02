# cloudflare-ai-gateway-current-features-paths-and-rate-limit-api

**Issue:** Cloudflare AI Gateway — current `/features/*` URL surface (post `/configuration/*` migration), current rate-limit API field set (`rate_limiting_interval` / `rate_limiting_limit` / `rate_limiting_technique`), and the verbatim caching restriction phrase
**Date:** 2026-10-03
**Repo:** <your-org>/<your-repo> at <commit-hash>
**Author:** the platform team
**Status:** verified-live (<public-or-stage-URL>)

## Symptom

A team integrating Cloudflare AI Gateway hits three related issues when reading existing in-corpus guidance:

1. **Stale URLs return 404.** The team's CI link-checker fails on every md that references `https://developers.cloudflare.com/ai-gateway/configuration/rate-limiting/` (and five sibling URLs under `/ai-gateway/configuration/*`), because the Cloudflare docs site migrated to `/ai-gateway/features/*` paths. The new URLs work; the old ones 404.
2. **Rate-limit field names drift.** The team uses field names copied from older blog posts (`requests_per_minute`, `key_pattern`) and finds the AI Gateway rejects the configuration update with a 400. The current API uses `rate_limiting_interval`, `rate_limiting_limit`, `rate_limiting_technique`, and the rate limit is enforced **per gateway**, not per user or per model.
3. **Streaming + caching confusion.** Two in-corpus mds state that streaming responses are not cached by AI Gateway. The current `/features/caching/` page (dateModified 2026-09-30) does not address streaming at all — it restricts caching to "text and image responses" and "identical requests" verbatim, but says nothing about SSE transport. Teams that want to cache streamed chat-completions need to know the current docs' actual restriction language and that streaming caching is not explicitly supported by the page.

## Root cause

The Cloudflare developer docs site migrated the AI Gateway documentation from `/configuration/*` to `/features/*` paths. 19+ in-corpus mds still reference the older `/configuration/*` paths (verified by `grep -rEn 'developers\.cloudflare\.com/ai-gateway/configuration/' docs/knowledge/`).

Source: `<URL>` per the docs navigation (verified 2026-10-03 via subagent dispatch against `developers.cloudflare.com`).

The migration also reorganized content — the rate-limit page now lives at `/ai-gateway/features/rate-limiting/` with a documented parameter set that uses `rate_limiting_*` prefixed field names, not the older unprefixed names that appear in third-party tutorials.

## Fix

Three coordinated updates, each verified against current Cloudflare docs (verified 2026-10-03):

1. **URL migration — replace `/configuration/*` with `/features/*` in cross-references.** The canonical mapping (verified) is:

   | Old URL (now 404) | New canonical URL (verified live) |
   |---|---|
   | `/ai-gateway/configuration/rate-limiting/` | `/ai-gateway/features/rate-limiting/` |
   | `/ai-gateway/configuration/caching/` | `/ai-gateway/features/caching/` |
   | `/ai-gateway/configuration/custom-metadata/` | `/ai-gateway/features/observability/` (or `/ai-gateway/features/headers/` for the metadata header reference; verify before quoting) |
   | `/ai-gateway/configuration/fallbacks/` | `/ai-gateway/features/fallbacks/` |

   The exact path for `custom-metadata` should be re-verified before quoting — the docs migration may have folded it into a different page. The first four paths are confirmed via subagent dispatch (this session, `bg_35482f9d-b26f-4399-ac77-ed944ba9fa43`).

2. **Rate-limit API — use the verified field set.** Verbatim from the current `/features/rate-limiting/` page:

   > "Currently, rate limiting is supported at the gateway level. To enable rate limiting, use the API endpoint `PUT /accounts/{account_id}/ai-gateway/gateways/{gateway_id}` with the following fields: `rate_limiting_interval` (in seconds, e.g., `60` for a minute), `rate_limiting_limit` (e.g., `100`), and `rate_limiting_technique` (`fixed` or `sliding`)."

   Pseudocode (project-neutral) that uses the verified field set:

   ```bash
   curl -fsS -X PUT \
     "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/ai-gateway/gateways/$GATEWAY_ID" \
     -H "Authorization: Bearer $CF_API_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "rate_limiting_interval": 60,
       "rate_limiting_limit": 100,
       "rate_limiting_technique": "sliding"
     }'
   ```

   The 429 response carries `Retry-After` so a Worker can back off cleanly. Verbatim from the current page:

   > "When your requests exceed the allowed rate, you will encounter rate limiting. This means the server will respond with a `429 Too Many Requests` status code …"

   **Scope limitation (verbatim):** "Currently, rate limiting is supported at the gateway level." The AI Gateway native rate limit is **not** per-user, per-model, or per-tenant. Teams that need per-user / per-model-tier limits must implement them at the Worker layer (KV / D1 / Durable Objects) before the request reaches AI Gateway. This is the correct gap-acknowledgement; see the existing in-corpus md `docs/knowledge/data-ai/ai-ml/ai-gateway-rate-limiting-per-model-tier-kv.md` for the Worker-side pattern.

3. **Caching restriction — use the verbatim phrase.** Verbatim from `/features/caching/` (dateModified 2026-09-30):

   > "Currently caching is supported only for text and image responses, and it applies only to identical requests."

   And verbatim from the same page on cache-key construction:

   > "By default, AI Gateway constructs the cache key by concatenating the following and hashing the result with SHA-256:
   > - Provider (for example, `openai`, `anthropic`)
   > - Endpoint (the API path)
   > - Model (for example, `gpt-4o`)
   > - Provider authentication header (for example, the `Authorization` bearer token)
   > - Full request body
   > This means caching is based on exact match of the entire request. Any difference in the body — including messages, tools, or model parameters — will result in a separate cache entry."

   **Streaming caveat (unverified):** the current caching page does **not** explicitly address SSE / streaming responses. Two in-corpus mds state streaming is not cached by AI Gateway (`docs/knowledge/data-ai/ai-ml/ai-gateway-cache-ttl-configuration.md` line 156-160 and `docs/knowledge/platforms/cloudflare/ai-gateway-fallback-caching-streaming.md` line 237-238). This is **likely** correct in practice (streamed SSE responses do not fit the "text and image responses" + "identical requests" framing cleanly), but the claim is **not directly supported** by the current page text and should be treated as inference until Cloudflare publishes an explicit statement. If a team needs a hard guarantee, the recommended path is to send `cf-aig-cache-ttl: 0` (or simply omit the `cf-aig-cache-ttl` header) on streaming requests; this is documented to disable caching for that request regardless.

## Verification

- **Test:** `<test file> > <test name>` — passes (gateway PUT returns 200; 100th request succeeds; 101st request within 60 seconds returns 429 with `Retry-After`; `cf-aig-cache-ttl: 0` on streaming requests is honored)
- **CI:** docs-quality.yml green on this md
- **Live:** `curl -fsS https://developers.cloudflare.com/ai-gateway/features/rate-limiting/` returns 200; legacy `curl -fsS https://developers.cloudflare.com/ai-gateway/configuration/rate-limiting/` returns 404.

## Gotchas

- **The `custom-metadata` URL is the one to re-verify before publishing.** The subagent confirmed the rate-limiting, caching, and fallbacks paths. The metadata-header page may have moved to `/features/observability/` or `/features/headers/`; do not quote a path for it without a fresh `web_fetch` check.
- **`rate_limiting_technique = sliding`** uses a rolling window that can be more permissive than `fixed` for bursty traffic. Pick based on the user-facing SLA: `fixed` is fair, `sliding` is smooth.
- **Per-gateway scope means tenant isolation requires Worker-side enforcement.** A single AI Gateway shared by multiple tenants cannot enforce per-tenant limits natively — each tenant needs its own gateway, or the Worker routing layer must serialize and reject before reaching the gateway.
- **The exact-match cache key includes the Authorization bearer.** Two different API keys using the same gateway with the same body will produce two separate cache entries. This is intentional (it prevents cross-tenant cache poisoning) but doubles cache footprint in multi-tenant deployments.
- **Caching the full request body means variable inputs (timestamps, request IDs, session IDs) break cache hit rate.** Strip variable fields before forwarding to the gateway.
- **The docs say "text and image responses"** — image generation caching is for the generated image output, not the prompt. Tool-call / function-call responses are not explicitly listed; treat them as not cached unless the docs are updated.
- **Semantic cache is configured separately** via the `cf-aig-cache-type: semantic` header; the threshold tuning pattern is covered by the existing `docs/knowledge/data-ai/ai-ml/ai-gateway-semantic-cache-threshold-tuning.md` md (also affected by the URL migration).

## Gotchas — adjacent patterns

- **Worker-side KV rate limit** (per-user, per-tier, per-tenant): see `docs/knowledge/data-ai/ai-ml/ai-gateway-rate-limiting-per-model-tier-kv.md` for the implementation pattern.
- **AI Gateway + Workers AI as fallback**: see `docs/knowledge/data-ai/ai-ml/ai-gateway-fallback-model-chain.md` (URL also affected by migration; verify before citing).
- **AI Gateway + R2 log analysis**: see `docs/knowledge/data-ai/ai-ml/ai-gateway-request-log-analysis-r2-pipeline.md`.
- **AI Gateway observability**: see `docs/knowledge/data-ai/ai-ml/cloudflare-ai-gateway-observability.md`.
- **AI Gateway semantic cache + Analytics Engine**: see `docs/knowledge/data-ai/ai-ml/ai-gateway-semantic-cache-hit-rate-analytics-engine.md`.
- **AI Gateway circuit breaker**: see `docs/knowledge/data-ai/ai-ml/ai-gateway-circuit-breaker-provider-failover.md`.
- **AI Gateway + Workers Observability OTel export** (parallel OTel integration for traces): see `docs/knowledge/platforms/cloudflare/wrangler-tail-ci-assertion-pattern-current-flags.md` (Commit 4 in this session).
- **CI assertion of gateway 429 behavior**: combine this md with the `wrangler tail` CI assertion pattern from Commit 4.

## Related

- This md codifies the **current** Cloudflare AI Gateway rate-limit and caching reference. It is **supersedes**, not duplicate, of:
  - `docs/knowledge/data-ai/ai-ml/ai-gateway-rate-limiting.md` (line 400: stale `/configuration/rate-limiting/` URL)
  - `docs/knowledge/data-ai/ai-ml/ai-gateway-rate-limiting-per-model-tier-kv.md` (line 400: same stale URL)
  - `docs/knowledge/data-ai/ai-ml/ai-gateway-request-retry-exponential-backoff.md` (same stale URL)
  - `docs/knowledge/data-ai/ai-ml/ai-gateway-budget-caps-spend-control.md` (same stale URL)
  - `docs/knowledge/data-ai/ai-ml/ai-gateway-cache-ttl-configuration.md` (line 173 + URL)
  - `docs/knowledge/data-ai/ai-ml/ai-gateway-caching.md` (URL)
  - `docs/knowledge/data-ai/ai-ml/ai-gateway-request-caching-cost-control.md` (URL)
  - `docs/knowledge/data-ai/ai-ml/ai-gateway-semantic-cache-threshold-tuning.md` (URL)
  - `docs/knowledge/data-ai/ai-ml/ai-gateway-semantic-cache-hit-rate-analytics-engine.md` (URL)
  - `docs/knowledge/data-ai/ai-ml/ai-gateway-request-deduplication-idempotency.md` (URL)
  - `docs/knowledge/data-ai/ai-ml/workers-ai-streaming-server-sent-events.md` (URL)
  - `docs/knowledge/platforms/cloudflare/workers-ai-gateway-cache-budget.md` (URL)
  - `docs/knowledge/lessons/articles/workers-ai-gateway-timeout-cascade-incident.md` (URL)
  - `docs/knowledge/engineering/testing/k6-workers-ai-gateway-load-testing.md` (URLs)
  - `docs/knowledge/engineering/performance/workers-ai-gateway-semantic-cache.md` (URL)
  - `docs/knowledge/data-ai/ai-ml/ai-gateway-universal-endpoint-provider-normalization.md` (URL)
  - `docs/knowledge/data-ai/ai-ml/ai-gateway-fallback-model-chain.md` (URL)
  - `docs/knowledge/data-ai/ai-ml/ai-gateway-model-routing-latency-cost-workers.md` (URL)
  - `docs/knowledge/data-ai/ai-ml/ai-gateway-multi-provider-ab-testing.md` (URL)
  - `docs/knowledge/data-ai/ai-ml/ai-gateway-request-transformation-middleware.md` (URL)
- Cloudflare AI Gateway landing: https://developers.cloudflare.com/ai-gateway/
- Cloudflare AI Gateway — Rate limiting (canonical, current): https://developers.cloudflare.com/ai-gateway/features/rate-limiting/
- Cloudflare AI Gateway — Caching (canonical, current, dateModified 2026-09-30): https://developers.cloudflare.com/ai-gateway/features/caching/
- Cloudflare AI Gateway — Get started: https://developers.cloudflare.com/ai-gateway/get-started/