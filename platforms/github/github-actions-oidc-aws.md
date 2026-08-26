# github-actions-oidc-aws

**Issue:** Authenticating GitHub Actions to AWS using OIDC without storing long-lived credentials
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Storing AWS access keys as GitHub Secrets is risky. OIDC lets Actions assume an IAM role directly using a short-lived token.

## Pattern / Solution
AWS IAM Identity Provider setup (one-time):
```
Provider URL: https://token.actions.githubusercontent.com
Audience: sts.amazonaws.com
```
IAM Trust Policy for the role:
```json
{
  "Effect": "Allow",
  "Principal": {
    "Federated": "arn:aws:iam::ACCOUNT:oidc-provider/token.actions.githubusercontent.com"
  },
  "Action": "sts:AssumeRoleWithWebIdentity",
  "Condition": {
    "StringEquals": {
      "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
    },
    "StringLike": {
      "token.actions.githubusercontent.com:sub": "repo:myorg/myrepo:ref:refs/heads/main"
    }
  }
}
```
Workflow:
```yaml
permissions:
  id-token: write
  contents: read
steps:
  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: arn:aws:iam::123456789:role/GitHubActionsRole
      aws-region: us-east-1
  - run: aws s3 ls
```

## Gotchas
- `id-token: write` permission is mandatory in the workflow.
- Scope the trust condition as tightly as possible (`sub` to specific repo + branch).
- The OIDC provider must be created once per AWS account.
- Wildcard `sub` conditions (`repo:myorg/*`) are dangerous — scope to the specific repo.

## Related
- `github-actions-oidc-cloudflare.md`
- `github-actions-oidc-gcp.md`
- `github-actions-secrets-management.md`
