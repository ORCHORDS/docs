# SOX Compliance Engineering Controls — Separation of Duties, Audit Trails, and CI/CD Gates

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your company is preparing for its first SOX (Sarbanes-Oxley) audit.
The auditor asks for evidence that the person who wrote a production
change is not the same person who approved and deployed it. Your
engineering team discovers that developers can self-approve PRs,
admins bypass branch protection, and deployment logs do not
capture who authorized each production release. The auditor flags
23 control deficiencies in the first week.

## Context

SOX Section 404 requires publicly traded companies to maintain
internal controls over financial reporting, including IT General
Controls (ITGC) that govern change management, access controls,
and audit trails for systems that touch financial data. Engineering
teams must enforce separation of duties (the person who writes code
cannot approve or deploy it), maintain immutable audit trails of
every control activity, and implement automated gates in CI/CD
pipelines. Continuous monitoring — always-on evidence capture from
CI/CD logs and access reviews — is increasingly favored over
quarterly manual evidence gathering. The first SOX fine for ITGC
failures can reach millions in remediation costs plus restatement
of financials.

## Core engineering controls

```
SOX ITGC engineering requirements:

  Control                  Implementation
  ──────────────────────────────────────────────────────────────
  Separation of Duties     PR author ≠ approver ≠ deployer
  Change Management        Every change linked to approved ticket
  Access Controls          Role-based, periodically recertified
  Audit Trails             Immutable, timestamped, attributed
  Continuous Monitoring    Automated evidence capture, not manual

  Retention: audit evidence typically retained 7 years.
```

## Branch protection configuration

```json
{
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": true
  },
  "required_status_checks": {
    "strict": true,
    "contexts": ["ci/tests", "ci/security-scan"]
  },
  "enforce_admins": true,
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
```

```
Critical settings for SOX compliance:

  dismiss_stale_reviews: true
    New commits invalidate prior approvals. Without this,
    code can be added after approval but before merge.

  enforce_admins: true
    Admins cannot bypass protection. This is the single
    most common SOX finding — admins silently defeating
    separation of duties.

  allow_force_pushes: false
    Force-push rewrites history, masking unauthorized changes
    and breaking the audit trail.
```

## CI/CD deployment pipeline

```
SOX-compliant deployment flow:

  1. Developer creates PR linked to approved ticket #<number>. CI runs tests + security scans (required status checks)
  3. Reviewer ≠ author approves PR (separation of duties)
  4. PR merged to protected branch
  5. Deployment job requires separate manual approval gate
     (GitHub Environments with required reviewers)
  6. Deployer ≠ author ≠ reviewer authorizes release
  7. Deploy action + approver identity + timestamp logged
     immutably to SIEM or audit-log sink

  Each step produces audit evidence:
  - Who wrote the code (commit author)
  - Who reviewed it (PR approver + timestamp)
  - What was reviewed (specific commit SHA)
  - Who deployed it (environment approver)
  - When it was deployed (deployment timestamp)
```

## Automated compliance gates

```yaml
# GitHub Actions — enforce ticket linking
- name: Enforce ticket reference
  run: |
    if ! echo "${{ github.event.pull_request.title }}" | \
      grep -qE '\[(JIRA|TICKET)-[0-9]+\]'; then
      echo "PR title must include ticket reference"
      exit 1
    fi

# Deployment environment with required reviewers
# (configured in repository Settings > Environments)
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: production
      url: https://app.example.com
    steps:
      - name: Deploy
        run: ./deploy.sh
```

## Anti-patterns

- **Developers self-approving PRs** — GitHub natively prevents
  self-approval in some configurations, but self-merge after
  another reviewer's stale approval is a frequent gap. Enable
  `dismiss_stale_reviews` to close this.
- **`enforce_admins: false`** — allows admins and org owners to
  bypass all branch protection, silently defeating separation of
  duties. This is the most common SOX finding in engineering teams.
- **Manual compliance checking** — relying on humans to remember
  control steps introduces inconsistency and audit findings. Encode
  compliance checks as CI gates with binary pass/fail outcomes.
- **Incomplete audit trails** — PRs merged without linked tickets,
  or review history that does not map to specific commits. Enforce
  ticket linking in CI and use immutable log storage.

## Gotchas

- **Stale-approval reuse** — merging new commits under an old
  approval (not dismissing stale reviews on push) breaks the
  "approved exactly this code" chain auditors need. Configure
  `dismiss_stale_reviews: true` on all protected branches.
- **Controls-as-code without documentation** — the control exists
  in practice but is not documented, so auditors cannot verify it.
  Keep control definitions (branch protection config, approval
  policies) in version control and auto-generate evidence reports.
- **Quarterly evidence scrambles** — gathering SOX evidence
  manually before each audit is expensive and error-prone. Use
  continuous monitoring with automated evidence capture from CI/CD
  logs and access review exports.
- **Shared service accounts for deployment** — defeats separation
  of duties because individual accountability is lost. Use
  individual identities with MFA for deployment authorization.

## Verification

- Branch protection enforces admin compliance (`enforce_admins: true`).
- Stale reviews dismissed on new commits.
- PR author cannot approve their own changes.
- Deployment requires separate approval from non-author personnel.
- All production changes linked to approved tickets.
- Audit logs exported to immutable storage with 7-year retention.
- Force-push disabled on all protected branches.

## Related

- `documentation/docs/policies/compliance/soc2-type2-audit-engineering.md`
- `documentation/docs/policies/github/actions-security-hardening.md`
- `documentation/docs/policies/lessons/technical-writing-rfcs-adrs.md`

## Source URLs (verified 2026-08-16)

- SOX Compliance for Software Delivery — https://www.harness.io/harness-devops-academy/sox-compliance-for-software-delivery-explained
- Code Review for Compliance: SOX, HIPAA, PCI — https://www.propelcode.ai/blog/code-review-compliance-sox-hipaa-pci-requirements
- SOX-Compliant CI/CD Integration — https://ones.com/blog/what-is-sox-compliant-cicd-integration-and-how-does-it-work/
- Best Practices for Automating SOX ITGC Evidence — https://screenata.com/resources/blog/best-practices-for-automating-sox-itgc-evidence-in-2026-from-access-controls-to-continuous-monitoring
