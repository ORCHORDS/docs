# fine-grained-pat-org-policy

**Issue:** Individual developers choosing fine-grained PATs over classic ones is a user-level decision (covered in `github-fine-grained-personal-access-tokens.md`); this article is the org-owner side — the policy layer that governs *every* credential class members can use against org resources. Since fine-grained PATs went GA in March 2025 and were enabled by default for all orgs, GitHub orgs have four independent policy surfaces to set: PAT access policy (allow vs restrict — restrict being the de-facto PAT zero-access mode), maximum token lifetime, admin approval for fine-grained tokens, OAuth app authorization restrictions, and deploy-key creation. Leaving each at its default means members can authorize arbitrary OAuth apps, mint 10-year classic PATs, and add read-write deploy keys to any repo they can admin. This article covers each policy, the service-identity decision tree (GitHub App vs fgPAT vs deploy key), and a safe enforcement order.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## PAT access policy: the three-dial model

1. **Dial 1 — Access: "Allow access via personal access tokens" vs "Restrict access via personal access tokens".** Restrict is the closest thing to a PAT zero-access mode: both fine-grained *and* classic PATs are blocked from org-owned private/internal resources. It is the setting to use when the org mandates GitHub Apps for automation. Note: SSH keys *created by* PATs continue to work under Restrict, and public repos in the org remain readable by any PAT regardless of policy — Restrict is not a total information barrier.
2. **Dial 2 — Maximum lifetime, set per token type.** Fine-grained tokens can be capped (default ceiling: 366 days); classic tokens historically have no expiration requirement, so a max-lifetime on classic is what actually kills the immortal `ghp_` token. Non-compliant tokens are *blocked, not revoked* — they start failing API calls, and users discover this at runtime, so announce before setting it.
3. **Dial 3 — Approval: "Require administrator approval" (default) vs not, fine-grained only.** With approval required, every member-created fine-grained PAT needs an org owner's sign-off before it touches org resources (owners' own tokens are exempt); owners get pending-request emails. Classic PATs are never subject to approval — the only way to govern them is dial 1 (Restrict).
4. **Enterprise overrides exist above org policy.** On Enterprise Cloud, an enterprise owner can set minimum policies that organization owners cannot loosen. Set the floor at the enterprise, leave friendly tuning to orgs.
5. **Fine-grained is on by default since GA (2025-03-18).** New orgs get fgPATs enabled unless the enterprise/org explicitly opts out — so "we never turned this on" is no longer a safe assumption during audits.

## OAuth app authorization policy

1. **Restrictions on/off.** With OAuth app access restrictions *enabled*, members and outside collaborators cannot authorize OAuth apps against org resources on their own; apps owned by the org itself are automatically allowed. New orgs ship with restrictions enabled by default — verify rather than assume.
2. **Enabling is disruptive the first time.** Existing unapproved apps immediately lose access: their API calls to private resources fail, webhook deliveries from private repos stop, and SSH keys created by OAuth apps stop working (users get a failure message with an approval URL). Schedule the flip.
3. **The flow: request, owner approve at app level.** Members request approval for a specific app; owners approve once per app (not per user), org-wide. Owners can additionally block outside collaborators from making requests at all.
4. **Disabling and re-enabling is forgiving.** If restrictions are re-enabled later, previously approved apps are automatically re-granted access — approvals are remembered.
5. **Known gap: no API.** There is no REST/GraphQL endpoint to read or change the OAuth app access policy; it is web-UI-only configuration. Put it in the runbook, not in Terraform.

## Deploy key hygiene

1. **Org-level toggle since GA (Oct 2024), under Settings → Member privileges → Deploy keys.** Enabled = members can create deploy keys on the org's repos; Disabled = nobody can. New orgs default to disallowed.
2. **Enterprise can enforce the floor.** An enterprise policy can prevent org owners from re-enabling deploy keys — the right shape for orgs standardizing on GitHub App-based deploys.
3. **Disabling is destructive.** Existing deploy keys across all repos are disabled, and any scripts/apps/workflows that create or use deploy keys stop working. Inventory before flipping (see enforcement order below).
4. **Deploy keys have no org visibility.** They are per-repo credentials, invisible in the org's credential views — which is precisely why they accumulate silently and why the org toggle plus `deploy_key` audit events are the only real controls. Prefer read-only keys where a pipeline only pulls; prefer a GitHub App wherever write is needed.

## Service identity decision tree (GitHub App vs fgPAT vs deploy key)

1. **Automation acting org-wide or on multiple repos → GitHub App.** Installation tokens (`ghs_`) are scoped to chosen repos and permissions, expire in ~1 hour, are attached to an identity the org controls (not to a person who can leave), and do not consume a seat. This is the answer for CI, bots, and internal tooling. See `github-apps-vs-pat.md` for the comparison and `github-apps-installation-tokens.md` for token mechanics.
2. **A person's script that touches a few repos with their own authority → fine-grained PAT.** Repo-selected, permission-scoped, expiring, and approval-gated by dial 3. Acceptable as the *exception* path when a GitHub App would be overkill.
3. **Single-repo, single-purpose machine clone/pull → read-only deploy key.** Narrowest blast radius for a build box that only needs `git fetch`. If it needs push, that is a smell — a GitHub App is the right primitive.
4. **Classic PAT → legacy, phase out.** No per-repo scoping, no approval workflow, SSO-authorized classic tokens survive offboarding until SAML/SCIM is airtight (see `github-saml-sso-enforcement.md`). Under the Restrict policy they simply stop working against the org, which is the intended end state.
5. **SAML interplay.** In SSO-enforced orgs, every PAT (classic and fine-grained) must be separately SSO-authorized or it fails against org resources — a common "my token works for public but 404s the org repo" cause.

## Enforcement order that avoids outages

1. **Inventory first.** Pull existing tokens, deploy keys, and authorized OAuth apps before touching policy: audit-log query for `pat.created`/`pat.grant`, `deploy_key.create`, and `oauth_application` events (see `github-audit-log-api.md`), plus the org's authorized OAuth apps view.
2. **Announce + set max lifetime.** Lowest breakage: publish the new ceiling, then set max lifetime per token type so non-compliant tokens fail *on their next renewal pressure*, not all at once.
3. **Require fgPAT approval.** Turns on the gate for new fine-grained tokens without touching anything already running.
4. **Migrate automations to GitHub Apps.** Move CI and bot credentials to installations; delete member-owned PATs as each migration lands.
5. **Flip Restrict + disable deploy keys last.** Only when inventory shows no remaining dependents. Watch the audit stream for denied-credential errors for a week after (`fine-grained-pat-org-policy` + `audit-log-streaming-siem.md` pair well here).
6. **Set the enterprise floor.** Once orgs are converged, lock the minimums at enterprise level so a new org cannot regress the posture.

## Related

1. **`github-fine-grained-personal-access-tokens.md`.** User-level token mechanics (prefixes, scoping) that these policies govern.
2. **`github-apps-vs-pat.md`.** Token-type comparison underlying the service identity tree.
3. **`github-saml-sso-enforcement.md`.** SSO authorization of PATs; the identity layer these policies sit on top of.
4. **`audit-log-streaming-siem.md`.** Alerting on `pat.created` and policy-change events during rollout.
5. **`corporate-org-setup-runbook.md`.** Where in the org setup sequence these five policy flips land.
