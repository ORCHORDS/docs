# SOC 2 Type II Controls for Engineering Teams

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

An enterprise prospect has requested a SOC 2 Type II report.
The engineering team is unsure which Trust Services Criteria
map to their day-to-day practices, what evidence the auditor
will collect, and how to close gaps before the observation
window opens.

## Context

SOC 2 is an AICPA attestation framework. A licensed CPA firm
assesses your controls against the Trust Services Criteria
(TSC). Type I is a point-in-time opinion ("controls are
designed appropriately"). Type II covers an **observation
period** (typically 6 or 12 months) and opines that controls
"operated effectively throughout the period." Prospects almost
always require Type II.

| Aspect        | Type I            | Type II                    |
|---------------|-------------------|----------------------------|
| Time scope    | Single date       | 6–12-month period          |
| Auditor work  | Design review     | Design + operating tests   |
| Typical cost  | $15k–$30k         | $30k–$80k+                 |
| Sales value   | Low               | High (enterprise standard) |

The five TSC categories are: Security (CC), Availability (A),
Confidentiality (C), Processing Integrity (PI), and Privacy
(P). Engineering is most accountable for the CC (Common
Criteria) series.

## 1. CC6 — Logical and Physical Access Controls

CC6.1 requires restricting logical access to authorized
internal and external users.

Key control evidence engineering must produce:

- **Access review records**: quarterly exports showing each
  engineer's repository, AWS, and production access,
  with reviewer signature and remediation of excess.
- **Joiner/mover/leaver log**: tickets showing access
  provisioned within SLA on joining, modified on role
  change, revoked within 24 hours of departure.
- **MFA enforcement**: screenshot or API evidence that MFA
  is required for all production systems (GitHub, AWS
  console, Cloudflare dashboard).

CC6.3 (least privilege) requires that access is limited to
what is needed. Use GitHub CODEOWNERS to enforce review on
sensitive paths and track privilege escalation requests:

```
# .github/CODEOWNERS
/infra/            @platform-team
/compliance/       @platform-team @security
/src/payments/     @payments-team @platform-team
```

Ensure branch protection rules are enabled and recorded:

```bash
# Verify branch protection via GitHub CLI
gh api repos/ORG/REPO/branches/main/protection \
  --jq '{
    required_reviews: .required_pull_request_reviews.required_approving_review_count,
    dismiss_stale: .required_pull_request_reviews.dismiss_stale_reviews,
    require_codeowners: .required_pull_request_reviews.require_code_owner_reviews,
    status_checks: .required_status_checks.contexts
  }'
```

Save this output monthly as CC6 evidence.

## 2. CC7 — System Operations

CC7.1 requires detecting and monitoring vulnerabilities and
configuration drift. CC7.2 requires that incidents are
identified, reported, and remediated.

Tooling requirements:

| Requirement           | Tooling example               |
|-----------------------|-------------------------------|
| Vulnerability scanning| Dependabot, Snyk, Trivy       |
| SIEM / log monitoring | Datadog, Splunk, Panther      |
| Uptime monitoring     | Cloudflare Health Checks      |
| Alert routing         | PagerDuty, OpsGenie           |

Evidence per audit cycle:
- Monthly dependency scan reports with ticket references
  for every HIGH/CRITICAL finding.
- Incident tickets with timestamps for detection, triage,
  resolution, and post-mortem.
- On-call rotation schedule and acknowledgement logs
  proving alerts were reviewed within SLA.

CC7.4 (incident response): maintain a tested IR plan.
Auditors often ask for evidence of a tabletop exercise or
actual incident response within the period.

## 3. CC8 — Change Management

CC8.1 requires that infrastructure and application changes
are authorized, tested, and approved before deployment.

Engineering controls that satisfy CC8.1:

```
Pull Request lifecycle (evidence required per PR):
  1. Feature branch created from protected main
  2. Automated CI passes (lint, test, security scan)
  3. ≥1 approving review from CODEOWNERS
  4. No unresolved review comments
  5. Squash-merge logged with PR number and reviewer
  6. Deployment ticket linked to PR number
```

Deployment pipeline gate (example GitHub Actions job):

```yaml
# .github/workflows/deploy.yml (excerpt)
deploy:
  needs: [test, security-scan]
  environment: production
  runs-on: ubuntu-latest
  steps:
    - name: Require approval
      uses: trstringer/manual-approval@v1
      with:
        approvers: platform-team
        minimum-approvals: 1
    - name: Deploy to Cloudflare Workers
      run: npx wrangler deploy --env production
```

Retain deployment logs including who triggered, who
approved, what was deployed, and the outcome. A 90-day
export satisfies most Type II audit requests.

## 4. CC9 — Risk Mitigation with Business Partners

CC9.2 requires assessing vendor risk. Engineering must
produce evidence that third-party integrations (Stripe,
SendGrid, Cloudflare, etc.) have been assessed.

Minimum vendor record per partner:

| Field                  | Example value              |
|------------------------|----------------------------|
| Vendor name            | Cloudflare, Inc.           |
| Services used          | Workers, D1, R2, Zero Trust|
| Data classification    | Confidential / PHI         |
| Latest SOC 2 report    | Type II, period to Aug 2025|
| Next review date       | 2026-08-01                 |
| Risk rating            | Low                        |

Request vendor SOC 2 reports annually via their trust
portal (trust.cloudflare.com). Store the report and
document your review.

## 5. Compliance Automation Tooling

Manual evidence collection does not scale. The following
platforms integrate with GitHub, AWS, and Cloudflare to
automate evidence gathering:

| Tool           | Approach         | Approx. cost/yr |
|----------------|------------------|-----------------|
| Vanta          | Agent + API pull | $15k–$40k       |
| Drata          | Agent + API pull | $15k–$40k       |
| Tugboat Logic  | Manual + guided  | $8k–$20k        |
| Scytale        | API + templates  | $10k–$30k       |

All four support CC6, CC7, and CC8 evidence collection out
of the box. Connect the GitHub integration first — it pulls
PR reviews, branch protection config, and access lists
automatically.

## Anti-patterns

- Collecting evidence only at audit time — auditors need
  continuous evidence spanning the observation window;
  retroactive collection will fail.
- Using personal GitHub accounts for any production
  operation — all actions must be traceable to a named,
  role-bound identity.
- Approving your own pull request — CC8 requires
  independent review; self-approval is a finding.
- Failing to document exceptions — if a control is not
  implemented, document why and what compensating control
  exists; silence is a gap.
- Giving contractors production access without the same
  provisioning/de-provisioning process as employees.

## Gotchas

- The observation period clock starts **immediately** — do
  not begin control implementation mid-period without
  noting the start date of each control in your tracker.
- Auditors sample evidence; they often request 25 of the
  last 90 deployments. Ensure your CI system retains logs
  longer than 90 days.
- SOC 2 does not specify technology; it tests whether
  your own stated policies are followed consistently.
  Write policies that reflect what you actually do, not
  what you intend to do.
- A Type II report from your previous auditor is not
  transferable — if you change firms you start a new
  observation period.

## Verification

1. Pull branch protection settings for `main` with the
   GitHub CLI command in section 1 and confirm all fields
   are set to required.
2. Export the access review spreadsheet for the most
   recent quarter — every active engineer should appear
   with a reviewer and no excess-access items outstanding.
3. Pick five merged PRs at random from the last 30 days
   and confirm each has ≥1 reviewer and passing CI.
4. Open your vendor risk register and confirm every
   vendor with production data access has a current
   (< 12 months old) SOC 2 report on file.

## Related

- `/compliance/soc2-cc6-logical-access-controls.md`
- `/compliance/soc2-cc7-system-operations.md`
- `/compliance/soc2-cc8-change-management.md`
- `/compliance/soc2-type1-vs-type2-certification-path.md`
- `/compliance/iso-27001-isms-scope-definition.md`

## Source URLs (verified 2026-08-17)

- https://www.aicpa-cima.com/resources/download/2017-trust-services-criteria
- https://us.aicpa.org/content/dam/aicpa/interestareas/frc/assuranceadvisoryservices/downloadabledocuments/trust-services-criteria.pdf
- https://vanta.com/products/soc-2
- https://drata.com/compliance/soc-2
- https://trust.cloudflare.com
