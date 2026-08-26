# GitHub Actions Native Egress Firewall (2026)

## Overview
The native Actions egress firewall is a 2026 roadmap capability that lets org
and enterprise admins define allow-lists for outbound network destinations a
job may contact, enforced at the runner/network layer rather than only via
self-hosted proxies. For GitHub-hosted runners this means a job with no
explicit allow-rule cannot exfiltrate build context, secrets, or source to an
attacker-controlled endpoint — even if a compromised action or dependency
attempts it.

This addresses the long-standing gap where `permissions:` locked down the
GitHub token, but a malicious step could still `curl` secrets to anywhere.

## Symptom
You discover (via audit log, secret-scanning push-protection follow-up, or a
post-incident review) that a workflow step exfiltrated an env var to
`https://evil.example.com/upload`. Classic signs that egress was unconstrained:
- A third-party action makes unexpected network calls to a domain you do not
  recognize.
- Secret-scanning alerts fire on tokens that only ever lived inside a CI env
  var, implying they were read and shipped out at runtime.
- A dependency's postinstall script reaches out to a telemetry/CDN endpoint
  that is not on any allow-list you intended.
- Bandwidth or build time spikes because a step is uploading the repo tarball.

## Gotchas
- The firewall is allow-list based. The first rollout will break legitimate
  calls (package registries, S3, your artifact store). Plan a "warn" period
  before flipping to "block".
- DNS-based rules alone are insufficient — a step can resolve a benign domain
  that then 302s to a malicious host. Prefer FQDN + path rules where supported
  and combine with TLS interception/logging on self-hosted runners.
- Package managers cache. A job that worked during the warn phase because of a
  warm cache can fail in block mode once the cache is evicted.
- `actions/checkout` and the runner's own control-plane traffic must be on the
  implicit allow-list or every job fails. Confirm these are exempt before
  applying a strict policy org-wide.
- Reusable workflows and composite actions bring their own network
  assumptions. The egress policy applies to the job, not the action, so a
  called reusable workflow that needs an external API must have that API in the
  caller's allow-list.
- OIDC token issuance (to `token.actions.githubusercontent.com`) is control
  plane; do not let an over-broad block rule break token exchange
  (`github-actions-oidc-aws.md`, `github-actions-oidc-gcp.md`).

## Policy Shape
```yaml
# Declared at org/enterprise level; shown here as a workflow-scoped annotation
# for documentation purposes. Actual enforcement is configured in org settings.
egress-policy:
  mode: block                  # warn | block
  default: deny
  allow:
    - host: github.com
      reason: "checkout + git"
    - host: "*.npmjs.org"
      reason: "package install"
    - host: "files.pythonhosted.org"
      reason: "pip"
    - host: "my-artifacts.s3.us-east-1.amazonaws.com"
      reason: "artifact upload"
  deny:
    - host: "*.example.org"     # explicit deny wins over allow globs
      reason: "known exfil domain"
```

## Rollout Plan
1. **Inventory.** Enable `mode: warn` org-wide for one sprint. Collect every
   destination that triggers a warning.
2. **Classify.** Split destinations into: known-good (add to allow-list),
   unknown (investigate the action that calls them), and clearly-malicious
   (add to deny-list, open an incident if the call came from a trusted action).
3. **Pilot block mode** on a single non-critical repo. Confirm builds stay
   green for a week.
4. **Expand** team by team, prioritizing repos that handle secrets, prod
   deploy keys, or customer data.
5. **Enforce enterprise-wide** with policy-as-code so future repos inherit it.

## Interactions With Other Features
- **Self-hosted runners:** the cloud-native firewall applies to GitHub-hosted
  runners; for self-hosted, mirror the policy in your VPC security groups
  (`github-actions-self-hosted-runners-2026.md`).
- **IP allow-lists** (`github-ip-allow-list.md`) control *inbound* to your
  resources; egress firewall controls *outbound* from the runner. They are
  complementary, not substitutes.
- **Secret scanning push protection** stops secrets entering the repo; egress
  firewall stops them leaving at runtime. Both needed.

## Debugging a Blocked Job
- The runner emits a structured log line for each denied connection including
  the host, port, and calling process. Filter logcat/logs for
  `egress.denied`.
- Temporarily switch the policy for that repo to `warn` and diff the allowed
  destinations against your expectation.
- Check whether the call originates from a `post:` step of an action — those
  run even when the main step failed, and are easy to overlook in review.

## Summary
The egress firewall closes the last wide-open door in Actions security: once
the token is locked down (permissions), inputs are reviewed (dependency
locking), and refs are pinned (SHA pinning), outbound network is the remaining
exfil vector. Treat it as the fourth pillar of Actions hardening.
