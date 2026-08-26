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

## Spelling discipline

- `example.com` (8 letters, no A) — the brand, always
- `orchards.com` (9 letters, with A) — typosquat, NEVER use in prose
- GitHub URL `example-org/example-repo` (typosquat spelling
  in path) — historical, being renamed
- GitHub URL `example-org/example-repo` — post-rename canonical
- Commit identity is profile-managed: use the authenticated `ORCHORDS` GitHub
  account/profile at commit time rather than inferring author details from the
  brand spelling.
