# workers-ai-current-paths-features-migration-from-configuration

**Issue:** Workers AI — current canonical URL split between `/configuration/` and `/features/`, with stale references to `/configuration/json-mode/` (now at `/features/json-mode/`) and a clarifying note that `/configuration/streaming/` was never a standalone page
**Date:** 2026-10-03
**Repo:** <your-org>/<your-repo> at <commit-hash>
**Author:** the platform team
**Status:** verified-live (<public-or-stage-URL>)

## Symptom

Corpus mds frequently link to `/workers-ai/configuration/json-mode/`, `/workers-ai/configuration/how-to-use-streaming/`, `/workers-ai/configuration/streaming/`, etc. Most of these land on 404. A team trying to follow a link from an old tutorial hits a dead end and is unsure whether (a) the doc moved, (b) the feature was renamed, or (c) they have a stale URL.

## Root cause

Cloudflare split Workers AI documentation in 2025–2026 into two URL trees:

- **`/workers-ai/configuration/`** — binding/integration setup (Workers Bindings, OpenAI-compatible API, Vercel AI SDK, Hugging Face Chat UI). These are *how to connect* docs.
- **`/workers-ai/features/`** — capability docs (JSON Mode, Function Calling, Fine-tunes, Batch API, Prompt Caching, Prompting, Reject busy, Markdown Conversion). These are *what you can do* docs.

Streaming is documented inline inside the `/configuration/*` integration pages (`/configuration/bindings/`, `/configuration/ai-sdk/`, `/configuration/open-ai-compatibility/`); there is **no standalone `/workers-ai/features/streaming/` page** and never has been one in the new tree.

Verified 2026-10-03 against `https://developers.cloudflare.com/workers-ai/llms.txt`. The "features" section in current llms.txt lists exactly: `batch-api`, `fine-tunes`, `function-calling`, `json-mode`, `markdown-conversion`, `prompt-caching`, `prompting`, `reject-if-busy`. `streaming` is absent (it lives in the `configuration` integration pages).

## Path-mapping table (verified)

| Stale URL in corpus                                | Current URL                                               | Notes                                                                                                    |
| -------------------------------------------------- | --------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `/workers-ai/configuration/json-mode/`             | `/workers-ai/features/json-mode/`                         | Page moved into the `features/` tree. `dateModified: 2026-09-14`.                                        |
| `/workers-ai/configuration/how-to-use-streaming/` | `/workers-ai/configuration/bindings/` (streaming section) | Old slug was retired. No `/features/streaming/` equivalent — read the streaming subsection of bindings/ai-sdk/open-ai-compatibility instead. |
| `/workers-ai/configuration/streaming/`             | Same — no standalone page; streaming is in `configuration/bindings/`, `configuration/ai-sdk/`, `configuration/open-ai-compatibility/` | 404s on direct visit; the feature is covered inline. |
| `/workers-ai/configuration/bindings/`              | **still current.**                                                | Lives under `configuration/` because it's an integration pattern.                                       |
| `/workers-ai/configuration/open-ai-compatibility/`| **still current.**                                                | Same reason.                                                                                             |
| `/workers-ai/configuration/ai-sdk/`                | **still current.**                                                | Same reason.                                                                                             |
| `/workers-ai/configuration/hugging-face-chat-ui/`  | **still current.**                                                | Same reason.                                                                                             |

So the migration rule is: **`json-mode` moved; everything else under `/configuration/` is still current**.

## Verbatim assertion from `features/json-mode/` page

> "JSON Mode currently doesn't support streaming."
> — `https://developers.cloudflare.com/workers-ai/features/json-mode/`, last updated 2026-09-14

A team that combines `response_format: json_schema` with `stream: true` will get a streaming chunk that is *not* structured JSON — plan to either turn streaming off or send the response through a downstream validator.

## Gotchas

- The new `features/` tree uses the sidebar group "Features" — link to `features/json-mode/` directly; do **not** chain through `/workers-ai/features/` (an index returns 404).
- Tutorials under `/workers-ai/guides/tutorials/` are unchanged; they continue to link out to the correct `features/` and `configuration/` pages.
- Some tutorial pages still mention the old `configuration/json-mode` slug — check with the current llms.txt before deep-linking from a tutorial.

## Verification

- **Live page (moved):** `https://developers.cloudflare.com/workers-ai/features/json-mode/` → 200 OK, dateModified 2026-09-14
- **Live llms.txt:** `https://developers.cloudflare.com/workers-ai/llms.txt` → 200 OK, lists `features: json-mode` and `configuration: bindings, open-ai-compatibility, ai-sdk, hugging-face-chat-ui` (no `streaming`, no `json-mode`)
- **Negative test:** `curl -sI https://developers.cloudflare.com/workers-ai/configuration/json-mode/` → 404
- **Negative test:** `curl -sI https://developers.cloudflare.com/workers-ai/features/streaming/` → 404

## Related / supersedes

- 25 corpus mds reference `/workers-ai/configuration/` paths (`grep -rln` count, 2026-10-03). Only those linking to `/configuration/json-mode/` are stale — verify each before reuse.
- The 2026 AI Gateway md (`docs/knowledge/data-ai/ai-ml/cloudflare-ai-gateway-current-features-paths-and-rate-limit-api.md`) addresses the parallel `/ai-gateway/configuration/` → `/ai-gateway/features/` migration; both migrations follow the same URL-shape rule (configuration is bindings; features are capabilities).
- `docs/knowledge/platforms/cloudflare/workers-ai-2026.md` and `docs/knowledge/data-ai/ai-ml/workers-ai-llm-cold-start-gpu-ai-inference.md` — verify before reuse; likely link to old `configuration/` paths correctly (bindings/AI SDK) but should be rechecked.
- 0 corpus mds currently reference `/workers-ai/features/streaming/` (correctly, because that path doesn't exist).