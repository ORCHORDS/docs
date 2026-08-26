# soc2-evidence-collection-automation

**Issue:** Automating SOC 2 evidence collection to reduce audit preparation burden
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Manual evidence collection for SOC 2 audits is time-consuming and error-prone. Compliance automation platforms and scripted collection reduce effort from weeks to hours.

## Pattern / Solution
Automation layers:

1. Compliance platforms (Vanta, Drata, Secureframe, Tugboat Logic):
   - Connect to AWS/GCP/Azure, GitHub, Okta, HR systems
   - Auto-collect: user lists, MFA enrollment, access reviews, vulnerability scan results
   - Continuous monitoring with compliance posture dashboard

2. Custom scripts for gaps:

```bash
# Export AWS IAM users with MFA status
aws iam generate-credential-report && \
aws iam get-credential-report --query 'Content' --output text | base64 -d > iam-report.csv

# List GitHub PR reviews (last 90 days)
gh api /repos/{owner}/{repo}/pulls?state=closed&per_page=100 > pr-reviews.json
```

3. Evidence naming convention:
   - Format: YYYY-MM-DD_control-id_description.ext
   - Example: 2026-07-01_CC6.2_access-review-Q2-approval.pdf

4. Evidence storage: dedicated S3 bucket with versioning; auditor read-only IAM role

5. Automated weekly evidence snapshot: Lambda/cron job pulling reports, saving to S3, tagging by control

## Gotchas
- Compliance platforms do not cover all controls — custom evidence still needed for vendor reviews, training, physical security
- Automated screenshots must show timestamp and context — bare CSV exports may be rejected
- Auditor access to evidence bucket must be provisioned before fieldwork starts (2-4 week lead time)
- Evidence from previous period can be used if control operates continuously — understand audit period boundaries

## Related
- `soc2-continuous-compliance.md`
- `soc2-type2-controls-mapping.md`
