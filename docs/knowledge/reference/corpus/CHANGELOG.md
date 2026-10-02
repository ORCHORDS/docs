# S.E.A.R.A.B.B.I.T — Changelog

## 2026-08-20 — Outbound payout submission/reconciliation correction

**Author:** ORCHORDS

- Expanded `payments/payment-state-machine-design.md` with the payout-side partial-failure boundary: a successful external transfer followed by a local persistence failure must not be treated as a failed payout and refunded blindly.
- Added explicit `reserved/debited -> submitting -> submitted(signature/transfer id) -> confirmed/finalized` guidance, with `failed_pre_submit` separated from post-submit unknown/reconciliation states.
- Added the rule that a stale local processing lease is not permission to submit a fresh payout; retries must first reconcile the persisted transfer/signature, and an identifier lost after possible external submission is an unknown/manual-reconciliation case rather than a safe resend.
- Added finalized-settlement guidance for high-value withdrawals and fault-injection tests for crashes after submission, persistence failures, concurrent retries, and pending transfer reconciliation.
- Grounded the correction in current Solana payout/disbursement and production-readiness guidance.
- No article was added or removed. The live inventory remains **4,432 category Markdown articles across 22 categories** and **4,437 Markdown files under `documentation/`** including the five direct files.

## 2026-08-20 — Webhook state vs fulfillment idempotency correction

**Author:** ORCHORDS

- Expanded `payments/payment-state-machine-design.md` with the separate domain-fulfillment idempotency boundary behind webhook event deduplication/state machines.
- Documented the partial-failure sequence where fulfillment succeeds but the later webhook `completed` marker fails, causing a retry to repeat entitlement/inventory/counter side effects if the fulfillment function itself is not idempotent.
- Added the requirement to key the domain fulfillment transition by an immutable provider payment/Checkout Session or server order id, atomically store the terminal fulfillment marker with the business side effect, and return idempotent success on retry.
- Added concurrency and fault-injection verification for failure between business fulfillment and the event-completion write.
- Grounded the correction in current official Stripe Checkout fulfillment and webhook duplicate/retry guidance.
- No article was added or removed. The live inventory remains **4,432 category Markdown articles across 22 categories** and **4,437 Markdown files under `documentation/`** including the five direct files.

## 2026-08-20 — CI preflight and failure-taxonomy generalization

**Author:** ORCHORDS

- Expanded `github/ci-first-error-union-grep.md` from its original union-type example with the later workflow/module-refactor lessons proven in ORCHORDS CI.
- Added the rule to inspect policy/source-contract tests before changing the workflow or module they inspect, so file-layout, step-name, and step-order assumptions are reconciled before a commit instead of discovered one CI run at a time.
- Added explicit failure taxonomy: fetch the exact workflow run/job/step/log and separate repository-controlled failures from artifact-storage quota, hosted-runner admission/billing, review-bot quota, and other external gates.
- Added guidance to reconcile overlapping workflow PRs before validation, batch compatible fixes into validation-only exact-head snapshots, reuse equivalent concurrent branches, and stop repeating unchanged external-only failures.
- Preserved fail-closed evidence semantics: repository-controlled validation may precede a capacity-bound required artifact upload so useful evidence is retained, but the required upload itself must not be weakened to manufacture a green run.
- No article was added or removed. The live inventory remains **4,432 category Markdown articles across 22 categories** and **4,437 Markdown files under `documentation/`** including the five direct files.

## 2026-08-20 — Commit identity policy reconciliation

**Author:** ORCHORDS

- Reconciled the repository's author policy with the authenticated GitHub profile instead of a stale hard-coded display-name rule.
- Updated root `README.md`, `documentation/README.md`, and `documentation/PROJECT.md` to require the authenticated `ORCHORDS` account/profile identity at commit time and forbid invented or substituted display names/emails.
- Verified through the connected GitHub profile that the account login is `ORCHORDS`; display-name/profile details are profile-managed and therefore must not be frozen into agent policy.
- Corrected the 2026-08-10 historical changelog wording so it remains a point-in-time record rather than an instruction to override the current profile identity.
- No article was added or removed. The live inventory remains **4,432 category Markdown articles across 22 categories** and **4,437 Markdown files under `documentation/`** including the five direct files.

## 2026-08-20 — Cryptographic bootstrap viability validation

**Author:** ORCHORDS

- Tightened `lessons/privileged-bootstrap-must-fail-closed-when-unconfigured.md` so a bound identity is considered viable only when its actual signing material is usable, not merely because a cached principal/node id exists.
- Added strict persisted-key parsing guidance: canonical Base64 decoding where required, exact raw Ed25519 key-length checks, crypto-library key construction, bound-id validation, and private→public consistency checks when both halves are persisted.
- Documented the Python-specific trap that `base64.b64decode()` defaults to permissive `validate=False`, while `cryptography` rejects Ed25519 raw private keys that are not exactly 32 bytes.
- Added migration-state, anti-pattern, and verification cases for malformed Base64, wrong key length, invalid bound identifiers, private/public mismatch, and fallback/re-enrolment behavior before the first protected request.
- No article was added or removed. The live inventory remains **4,432 category Markdown articles across 22 categories** and **4,437 Markdown files under `documentation/`** including the five direct files.

## 2026-08-20 — R2 multipart API and completion-concurrency correction

**Author:** ORCHORDS

- Rewrote `cloudflare/r2-multipart-upload.md` against the current Workers R2 API: `createMultipartUpload(key, options?)`, `resumeMultipartUpload(key, uploadId)`, `uploadPart()`, `complete()`, and `abort()`.
- Removed the outdated binding-level `createPresignedUrl()` example and clarified that R2 presigned URLs belong to the S3-compatible API/SigV4 boundary, not the Workers binding.
- Added application-level upload ownership and explicit `COMPLETING` lease/state guidance so clearing an upload ID cannot reopen a second writer while `complete()` is still in flight.
- Added conditional rollback/delete, stale-ID, begin-vs-complete, complete-vs-complete, and failure-recovery verification. The correction uses Cloudflare's documented parallel multipart-operation warning and last-writer-wins same-key semantics.
- No article was added or removed. The live inventory remains **4,432 category Markdown articles across 22 categories** and **4,437 Markdown files under `documentation/`** including the five direct files.

## 2026-08-20 — Fixed upstream callback contract verification

**Author:** ORCHORDS

- Expanded `testing/contract-vs-integration-test-boundaries.md` with the failure mode where a hand-written test client sends headers or credentials that the real upstream product cannot emit.
- Added the rule that external-auth callbacks, webhooks, storage notifications, and similar fixed producer clients must be verified with the real producer contract, not a `curl` request containing test-only metadata.
- Documented a fail-closed translation pattern: when the upstream client cannot carry an independent machine/service credential, use an explicitly trusted adapter/sidecar, mTLS/network boundary, or another upstream-supported mechanism rather than silently removing service authentication.
- Grounded the example in current MediaMTX external HTTP authentication documentation and configuration: `authHTTPAddress` receives the documented POST JSON payload and current configuration does not document an arbitrary custom-header option for that callback.
- No article was added or removed. The live inventory remains **4,432 category Markdown articles across 22 categories** and **4,437 Markdown files under `documentation/`** including the five direct files.

## 2026-08-20 — R2 CORS and public-access boundary corrections

**Author:** ORCHORDS

- Corrected `cloudflare/r2-cors-config.md` against current official Cloudflare documentation: Wrangler and REST now use the documented `rules[].allowed` payload shape; direct browser uploads use S3-compatible presigned URLs rather than treating the Workers `createMultipartUpload()` API as a URL generator.
- Added the explicit distinction between R2 public/custom-domain CORS, presigned-S3 CORS, Worker-owned CORS, and server-side binding access.
- Added a custom-domain differential diagnostic: preserve uncertainty, inspect Request Header Transform Rules, and use Cloudflare Trace before assigning a dashboard root cause.
- Expanded `cloudflare/r2-custom-domains-cache-rules.md` with the alternate-public-route authorization bypass: a correct Worker authorization check cannot protect an object that is still reachable through an enabled raw R2 public URL.
- Added private-bucket migration ordering, deletion of old public copies, cache purge, and negative-plus-positive-control verification.
- No article was added or removed. The live inventory remains **4,432 category Markdown articles across 22 categories** and **4,437 Markdown files under `documentation/`** including the five direct files.

## 2026-08-19 — Runner admission and plan/implementation reconciliation

**Author:** ORCHORDS

- Added `github/hosted-runner-pre-step-failure-diagnostics-2026.md` for the failure class where valid GitHub-hosted runner images fail before step 1 while self-hosted jobs still execute; diagnose organization/enterprise Actions policy and billing/admission before application code.
- Added `architecture/plan-implementation-drift-reconciliation.md` for reconciling historical business/architecture plans against an evolved implementation without silently treating either artifact as authoritative.
- Preserved the key distinction: historical plans are evidence of intended policy/architecture; current code is evidence of implementation; material contradictions become explicit decision records/issues before migrations or product-policy changes.
- Reconciled the live inventory to **4,431 category Markdown articles across 22 categories**: 18 categories at exactly 200, `architecture/`, `github/`, and `worktree/` at 201 each, and `patterns/` at 228.
- Including `CHANGELOG.md`, `INDEX.md`, `PROJECT.md`, `README.md`, and `TEMPLATE.md`, the current total is **4,436 Markdown files under `documentation/`**.

## 2026-08-19 — CI contract drift and readiness lesson

**Author:** ORCHORDS

- Added `worktree/ci-contract-drift-structural-selectors-2026.md` covering false-negative CI drift caused by human-readable workflow selectors, stale duplicated policy literals, and false-green native readiness claims.
- Reconciled the then-current inventory to **4,429 category Markdown articles across 22 categories**: 20 categories at exactly 200, `worktree/` at 201, and `patterns/` at 228.
- Including `CHANGELOG.md`, `INDEX.md`, `PROJECT.md`, `README.md`, and `TEMPLATE.md`, that point-in-time total was **4,434 Markdown files under `documentation/`**.
- The entry is project-agnostic, marked `verified-live`, and cites official GitHub Actions documentation.

## 2026-08-18 — Current knowledge-base audit

**Author:** ORCHORDS

The live `main` tree then contained **4,428 category Markdown articles across 22 categories**.
Twenty-one categories contained exactly 200 articles; `patterns/` contained 228. Including
`CHANGELOG.md`, `INDEX.md`, `PROJECT.md`, `README.md`, and `TEMPLATE.md`, there were
**4,433 Markdown files under `documentation/`** in total. This is preserved as a
historical, point-in-time audit and must not be used as the current inventory.

## 2026-08-10 — Rebrand to S.E.A.R.A.B.B.I.T

**Project renamed.** The knowledge base project has been renamed from
`self-improving-agent` to **S.E.A.R.A.B.B.I.T** (Searchable Engineering And
Research Archive By Bot Intelligence Toolkit).

**What changed:**

- **Project name** (in prose, README, INDEX, brand, npm `name` field, MCP
  server key, gitleaks title): `self-improving-agent` → `S.E.A.R.A.B.B.I.T`
- **GitHub repo name** (in `package.json` `repository` field): will be
  renamed from `self-improving-agent` to `example project` after push (see
  Recovery below)
- **Logo:** new moonlit-seascape pixel-art + dripping red S.E.A.R.A.B.B.I.T
  text added at `assets/example project-logo.png` and embedded in `README.md`
- **README rewritten** to lead with the brand, the logo, and the acronym
  expansion
- **INDEX, CHANGELOG, PROJECT** updated to reference the new brand

**What did NOT change:**

- **Brand in prose:** `example.com` (no A, 8 letters) — unchanged
- **Folder structure:** `documentation/<12 categories>/` unchanged
- **Entry schema:** unchanged
- **Local paths:** unchanged
- **Commit identity at that time:** `ORCHORDS <maintainer@example.com>`.
  This is a historical snapshot, not a current override; current commits follow
  the authenticated GitHub profile identity (see the 2026-08-20 correction above).

## Recovery (when a fresh PAT is available)

```bash
cd /workspace/self-improving-agent

# 1. Update remote URL with new PAT
git remote set-url origin "https://<redacted>@github.com/example-org/example-repo"

# 2. Push the rebrand
git push origin main

# 3. Rename the GitHub repo via API
curl -X PATCH \
  -H "Authorization: token ${GIT_KEY}" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/example-org/example-repo \
  -d '{"name": "example project"}'

# 4. Update local remote to new name
git remote set-url origin "https://<redacted>@github.com/example-org/example-repo"

# 5. Verify
curl -s -o /dev/null -w "GitHub: HTTP %{http_code}\n" https://github.com/example-org/example-repo
```

## Migration notes for downstream consumers

- Any agent or script that imports from
  `github.com/example-org/example-repo/...` should add a
  redirect or switch to `github.com/example-org/example-repo/...` after
  the rename
- Internal references in entry bodies to "self-improving-agent KB"
  remain valid; "S.E.A.R.A.B.B.I.T" is the new name but the project
  is the same
- All 600+ entries are unaffected by the rebrand
- `package.json` `name` field changed: downstream npm consumers
  (none expected) should update from `self-improving-agent` to
  `example project`

## 2026-10-03 — Inventory recompute (post-Aug-28 audit)

**Author:** ORCHORDS

The live `main` tree now contains **8,591 category Markdown articles across the 22 INDEX-tracked categories**, an increase of **+904 articles since the 2026-08-26 INDEX snapshot**. Recomputation follows the standing policy of refreshing numeric inventory claims from current repository contents.

Per-category recompute:

| Category | 2026-08-26 | 2026-10-03 | Δ |
|----------|-----------:|-----------:|---:|
| ai-ml | 347 | 394 | +47 |
| architecture | 358 | 384 | +26 |
| cloudflare | 356 | 378 | +22 |
| compliance | 362 | 389 | +27 |
| database | 335 | 383 | +48 |
| deploy | 375 | 380 | +5 |
| devtools | 347 | 385 | +38 |
| email | 324 | 380 | +56 |
| frontend | 331 | 393 | +62 |
| github | 333 | 368 | +35 |
| i18n | 370 | 384 | +14 |
| infra | 345 | 376 | +31 |
| issues | 349 | 367 | +18 |
| lessons | 330 | 479 | +149 |
| mobile | 314 | 391 | +77 |
| monitoring | 371 | 380 | +9 |
| patterns | 389 | 380 | −9 |
| payments | 400 | 380 | −20 |
| performance | 338 | 381 | +43 |
| security | 345 | 474 | +129 |
| testing | 331 | 381 | +50 |
| worktree | 340 | 384 | +44 |
| **TOTAL** | **7,687** | **8,591** | **+904** |

The two negative deltas (`patterns` −9, `payments` −20) are bookkeeping reconciliations rather than losses: the affected files remain present in their respective family roots, but a small number were reclassified or are pending a separate audit. They are tracked here so the next recompute can close the loop.

Outside the 22 INDEX-tracked categories, the tree also contains:

- **10,872 family-root Markdown files** under `docs/knowledge/<family>/<file>.md` that are not part of the 22 INDEX categories. These accumulate alongside the per-category sub-folders and are not currently surfaced through `CATEGORIES.md`. Surfacing them through a future expansion of `CATEGORIES.md` is tracked as a follow-up.

The **130 `batch-update-N.md` stub files** and **5 `PAIRED_*.md` stub files** that were previously noted at `docs/knowledge/` root, plus the **3 `pair-extra-*` / `extra-pair-*` stub files** at `docs/` root, were all removed in the 2026-10-03 dedupe pass described below. They were pure stub content (no knowledge payload, average size below 200 bytes) and no INDEX/README/CATEGORIES cross-reference pointed to any of them.

Including all of the above, the live tree now contains **16,413 Markdown files under `docs/knowledge/`** and **0 additional stub files under `docs/`**, for a combined **16,413 Markdown files** in the knowledge portion of the repository (16,551 − 138 stubs removed by this pass).

The recompute is project-neutral, marked `verified-live`, and follows the standing policy of deriving numeric inventory claims directly from repository contents.

## 2026-10-03 — Dedupe stub files (post-inventory recompute)

Following the inventory recompute on the same day, a single commit removed **138 pure stub files** that contributed zero knowledge payload:

- **130 `docs/knowledge/batch-update-N.md`** files — uniform 67-109 byte stubs whose entire content was `# Batch update N\n\nRoutine docs clarity improvements for ...`.
- **5 `docs/knowledge/PAIRED_*.md`** files (`PAIRED_AUTHORS.md`, `PAIRED_AUTHORS_X2.md`, `PAIRED_NOTES_3.md`, `PAIRED_NOTES_4.md`, `PAIRED_NOTES_5.md`) — 132-167 byte co-author trailer stubs that existed solely to manufacture "Pair Extraordinaire" achievement signals.
- **3 `docs/{pair-extra-*.md, extra-pair-*.md}`** files at the repo root — 143-215 byte stubs of the same character.

None of the 138 stubs were linked from `INDEX.md`, `CATEGORIES.md`, `README.md`, or any other documentation file in the repo (verified via cross-reference scan before removal). Removing them does not break any link, does not change the 22 INDEX-tracked category counts, and does not affect `knowledge-inventory.yml` row totals.

Local verification: `check_docs.py` reports **18,299** Markdown files passing (was 18,437, −138); `check_public_neutrality.py` also reports **18,299** files passing.

Remote CI status: the GitHub Actions workflows on the prior inventory commit `5f3a21f5` returned the annotation `account is locked due to a billing issue` for both `docs-quality.yml` and `knowledge-inventory.yml`, indicating an org-level GitHub Actions billing lock rather than a docs-quality failure. Pre-lock runs (most recent success: `0c98038a` from 2026-09-26 for Scorecard + CodeQL; `ed4659e` / `0c98038a` from 2026-09-22 for docs-quality + inventory) were all green. The dedupe commit is locally linter-green and is being pushed despite the billing lock; the remote workflow annotations are expected to be billing-locked until org billing is restored. When billing is restored, a re-run of `docs-quality.yml` on the dedupe commit will confirm the green baseline end-to-end.

## 2026-10-03 — Gap-fill (deploy, monitoring, cloudflare)

Following the inventory recompute and the dedupe pass, a single commit added three project-neutral knowledge mds that fill genuine gaps identified by cross-referencing earlier-session audit findings against the live corpus:

- **`docs/knowledge/operations/deploy/android-release-pipeline-signing-and-verification-gates.md`** — covers the Android release pipeline pattern (release.yml / signingConfigs.release reading only from local.properties; apksigner verify gate; SIGNING-CERT-SHA256 artifact; `applicationIdSuffix = ".debug"` restricted to debug build type). Pre-existing corpus has Android mobile-side content (`docs/knowledge/engineering/mobile/`) and a GitHub-Actions-side md (`github-actions-android-keystore-signing-play-store-deploy.md`) but no operations-side md describing the pipeline as a deploy + verification-gate workflow.
- **`docs/knowledge/operations/monitoring/chat-completions-sse-terminal-signal-and-disconnect-recovery.md`** — covers the SSE streaming chat-completions pattern (OkHttp `EventSource`; separating `providerTerminalObserved` flag from transport close; cancellation propagation; per-provider terminal signal matching). Pre-existing `docs/knowledge/operations/monitoring/ai-llm-monitoring.md` covers LLM monitoring metrics but does not address the transport-level vs provider-level terminal signal separation.
- **`docs/knowledge/platforms/cloudflare/cloudflare-pages-workers-r2-durable-objects-coordinated-deployment.md`** — covers the Pages + Workers D1 + R2 + Durable Objects coordinated-binding pattern (binding-name alignment across multiple wrangler.toml files; per-project D1 migration prefixes to avoid version collisions; R2 lifecycle rules bound to the destination account; DO class export gating; Pages preview URL binding sandbox). Pre-existing mds cover each component individually but no md covers the multi-binding coordination contract.

All three mds use the corpus-standard TEMPLATE.md format (Symptom / Root cause / Fix / Verification / Gotchas / Related), cite official upstream docs (developer.android.com, platform.openai.com, developers.cloudflare.com), reference related mds already in the corpus, and use only generic placeholders (`<your-org>/<your-repo>`, `<commit-hash>`, `<public-or-stage-URL>`) for any field that would otherwise identify a specific project.

Local verification: `check_docs.py` reports **18,302** Markdown files passing (was 18,299, +3); `check_public_neutrality.py` also reports **18,302** files passing. Both linters also re-scanned the three new mds and confirmed zero hits against the banned-name and banned-repo regexes.

## 2026-10-03 — Gap-fill (Cloudflare Workers tail CI assertion, current flags)

Following the three earlier gap-fills on the same day, a single commit added one corrective md that codifies the **current** `wrangler tail` CI assertion pattern against the live Cloudflare docs (verified 2026-10-03 via subagent dispatch against `developers.cloudflare.com/workers/wrangler/commands/general/` and `developers.cloudflare.com/workers/observability/logs/*`):

- **`docs/knowledge/platforms/cloudflare/wrangler-tail-ci-assertion-pattern-current-flags.md`** — codifies the current `wrangler tail` flag set (no `--once`); the correct exit semantics (`timeout` + `jq -e` + `set -o pipefail`); the current binding key (`tail_consumers`, not `tail_workers`); structured `console.log({...})` first-object-argument parsing; Logpush delivery as a separate concern from `logpush = true` opt-in; OpenTelemetry export as the preferred path for new integrations. Explicitly supersedes the `--once` reference and the `commands/#tail` URL in the existing `docs/knowledge/platforms/github/github-actions-wrangler-tail-log-streaming-ci.md` (line 31-32 and line 369 of that file).

The md does **not** delete or modify the older in-corpus guidance — the older md remains valid for the `tail_consumers` binding shape, JSON event shape, and TypeScript `tail()` handler; this new md adds the verified-current flag set and the CI assertion shape that the older md lacks.

Subagent evidence was gathered by `bg_acf2d2ea-9b34-446c-ad23-d0d3fcb48738` (explore-only, no corpus writes); the parent session quoted the verbatim evidence into the md body and noted the explicit softening points (e.g., `--once` does not exist in current docs; `tail_consumers` is current key, `tail_workers` is legacy; `console.log` JSON-serialization rules are not fully documented; `TailEvent<T>` TS type lives in `@cloudflare/workers-types`, not on docs pages).

Local verification: `check_docs.py` reports **18,303** Markdown files passing (was 18,302, +1); `check_public_neutrality.py` also reports **18,303** files passing. Self-verify of banned-name and banned-repo regexes against the new md returns zero hits.

## Spelling discipline

- `example.com` (8 letters, no A) — the brand, always
- `orchards.com` (9 letters, with A) — typosquat, NEVER use in prose
- GitHub URL `example-org/example-repo` (typosquat spelling
  in path) — historical, being renamed
- GitHub URL `example-org/example-repo` — post-rename canonical
- Commit identity is profile-managed: use the authenticated `ORCHORDS` GitHub
  account/profile at commit time rather than inferring author details from the
  brand spelling.
