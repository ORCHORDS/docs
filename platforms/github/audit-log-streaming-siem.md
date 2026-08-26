# audit-log-streaming-siem

**Issue:** Polling the audit log REST API (see `github-audit-log-api.md`) works for spot checks, but it inherits GitHub's 180-day retention window, burns rate limit, and can miss short bursts between polls. Audit log *streaming* is the enterprise-only capability that pushes audit and Git events continuously to your SIEM — but it is configured at the enterprise-account level (a Team org cannot use it at all), supports a specific set of destinations (S3, Azure Blob/Event Hubs, GCS, Datadog, Splunk, and a preview Purview path), delivers *at-least-once* (duplicates happen), and has operational traps: a stream paused more than seven days drops buffered history, Datadog rejects logs older than 18 hours, and a misconfigured endpoint must be fixed within six days or events are silently lost. This article covers destination setup, stream-vs-API trade-offs, retention design, and alerting patterns on high-signal events like `pat.created` and disabled branch protection.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Destinations and setup mechanics

1. **Scope: enterprise account only.** Streaming is configured under enterprise Settings → Audit log → Log streaming → Configure stream → Check endpoint → Save, and it covers *all organizations in the enterprise* from the moment it is enabled. Org-level streaming does not exist; Team orgs are limited to API polling. (This is a plan-tier gate — see `plan-selection-free-team-enterprise.md`.)
2. **Amazon S3.** Two auth modes: static access keys (IAM policy limited to `s3:PutObject` on a public-access-blocked bucket) or OIDC — add GitHub's OIDC provider (`https://oidc-configuration.audit-log.githubusercontent.com`, audience `sts.amazonaws.com`) and a role whose trust policy `sub` matches `https://github.com/ENTERPRISE` (case-sensitive). OIDC mode is unavailable for data-residency deployments; there is optional CloudTrail Lake integration.
3. **Azure Blob Storage vs Azure Event Hubs.** Blob: paste a SAS URL scoped to `Create`+`Write` on the container. Event Hubs: namespace + hub name + the shared-access policy's "Connection string—primary key". Neither works in Azure Government; Event Hubs plus IP firewall rules is unsupported with data residency.
4. **Google Cloud Storage.** Service account with a JSON key; the account needs no IAM role at creation, only "Storage Object Creator" on the target bucket; paste bucket name + full JSON key.
5. **Datadog.** Simplest — API key/client token + site selection, no bucket management. Query landed logs with `source:github.audit.streaming`. Caveat: Datadog rejects logs older than 18 hours, so any stream pause risks permanent loss.
6. **Splunk.** HEC endpoint must accept HTTPS (validated at `<domain>:<port>/services/collector`). Splunk Cloud domains are `http-inputs-<host>` on 443 (trials: `inputs.<host>` on 8088). Keep SSL verification on.
7. **Microsoft Purview (public preview).** EMU/data-residency enterprises only, and Copilot agent session events only — not a general audit sink today.
8. **Multiple endpoints are supported simultaneously (public preview).** Useful during SIEM migrations; duplicate delivery is expected.

## Stream format and operational limits

1. **Delivery format.** Compressed JSON files landing at `YYYY/MM/HH/MM/<uuid>.json.gz` (bucket/container paths). At-least-once semantics: build dedup on event UUID into the ingestion pipeline — duplicates are a documented behavior, not an error.
2. **The 7-day pause buffer.** Pausing a stream buffers up to 7 days; resuming after a 1–3 week pause replays only the last week; after 3+ weeks paused, the stream resumes *fresh from now* — the gap is gone forever. If your SIEM is down longer, plan an API backfill.
3. **Health checks every 24 hours.** Misconfigured streams email enterprise owners; you get 6 days to fix the endpoint before events start dropping. Route those emails to a monitored channel, not an owner's inbox.
4. **Egress allow-listing.** GitHub's `meta` REST API exposes a `hooks` key listing streaming source IP ranges — allow-list those in your destination's firewall before enabling, not after the first health-check failure.
5. **Enable API request events separately.** Beyond audit + Git events, Audit log settings can opt in to streaming of *security-relevant* API requests — not all endpoints, so do not treat the stream as a full API access log.

## Streaming vs REST API polling — what each is for

1. **Retention is the decisive difference.** GitHub keeps org/enterprise audit data for 180 days in the UI/API; streaming makes *your* SIEM's retention the only limit — i.e., streaming is the compliance answer for 1-year+ evidence requirements.
2. **Coverage differs.** The stream includes audit events *and Git events* for all enterprise orgs; the REST API (`/orgs/{org}/audit-log` or `/enterprises/{enterprise}/audit/log`) is per-org, paginated, rate-limited, and best for backfill, ad-hoc investigation with `phrase=` filters, and scripts (see `github-audit-log-api.md`).
3. **Latency and reliability.** Streaming is near-real-time with no polling cost; polling at high frequency trades rate limit for freshness and can miss events between window boundaries if a poll fails.
4. **Run both.** The standard pattern: stream as the system of record into SIEM storage, keep a `gh api ... --paginate` backfill script for gaps (post-incident, post-pause), and use the UI export (up to 100 MB / 10 minutes of processing) for one-off compliance dumps.
5. **Access control asymmetry.** Streaming is an enterprise-owner setting; the API is available to org owners and enterprise admins — meaningful when deciding who can read security telemetry.

## What the stream covers

1. **Management-plane audit events.** Org/enterprise settings changes, member and team changes, app and credential events (`pat.created`, `oauth_authorization`, deploy key creation), ruleset and branch protection changes.
2. **Git events.** Push/pull activity records — what distinguishes streaming from the API's default audit-only view and what makes insider-exfiltration detection feasible.
3. **Optional: security-relevant API requests.** Opt-in stream of API calls touching sensitive endpoints (a subset — verify coverage against your threat model before relying on it).
4. **Preview: Copilot agent session activity.** EMU/data-residency enterprises via the Purview integration — relevant if AI usage auditing is on your requirements list.

## Alerting patterns on key events

1. **Credential creation: `pat.created` (and `pat.grant`/renewals).** Alert on any fine-grained or classic PAT created by non-owner members — pairs with the approval policy from `fine-grained-pat-org-policy.md`; a spike outside working hours is the classic exfil precursor.
2. **Membership changes: `org.member_added`, `org.invite`, `team` changes.** Alert on member adds that did not originate from a SCIM reconciliation window — a manual add in a SCIM-managed org violates the IdP-as-source-of-truth rule from `scim-provisioning-lifecycle.md`.
3. **Protection removal: `branch_protection` disabled / ruleset deleted or deactivated.** The highest-signal pre-push-manipulation event; alert immediately and auto-open an incident with the actor and repo from `data.*` fields.
4. **Credential-survival anomalies: `user.suspend` storms.** Mass `user.suspend` outside a known offboarding batch suggests IdP misconfiguration cascading into SCIM (see `scim-provisioning-lifecycle.md`).
5. **SCIM health: `external_group.scim_api_failure`.** Repeated failures mean group sync is broken — team memberships are silently drifting from the IdP.
6. **Event field shape for detection rules.** Records carry `action`, `actor`, `org`, `repo`, `created_at` (epoch ms), and a `data.*` object (e.g., `data.target_login`, `data.team`, `data.hook_id`) — write detections against `action` + `actor` combos and enrich from `data.*`, and dedup on event UUID.

## Related

1. **`github-audit-log-api.md`.** The REST/polling counterpart — `gh api` recipes, `phrase` filters, export limits.
2. **`plan-selection-free-team-enterprise.md`.** Streaming as the enterprise-tier justification line for security review.
3. **`fine-grained-pat-org-policy.md`.** The policy layer whose violations these alerts detect.
4. **`scim-provisioning-lifecycle.md`.** Lifecycle events (`user.suspend`, SCIM failures) worth alerting on.
5. **`corporate-org-setup-runbook.md`.** Where stream enablement sits in the org setup order (after enterprise account creation, before member invite waves).
