# GitHub Repository Transfer Ownership Security

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to transfer a example project repository from a personal account to the
`your-org` organisation (or between organisations), or vice-versa. Transfers
seem straightforward in the UI but carry significant security implications:
deploy keys are dropped, team permissions are reset, GitHub Actions secrets are
lost, Cloudflare API tokens stored as repo secrets become inaccessible, and
existing CI runs break silently. This article is the runbook to audit before,
execute safely, and harden after a transfer.

---

## Context

A repository transfer in GitHub:

1. Changes the repository's namespace (URL changes from `old-owner/repo` to
   `new-owner/repo`).
2. GitHub creates a redirect from the old URL for **up to 1 year**.
3. Removes all **deploy keys** on the repository.
4. Removes all **repository-level Actions secrets and variables**.
5. Removes all **Dependabot secrets**.
6. Preserves issues, pull requests, wikis, releases, and git history.
7. Resets **team access** — the repo must be re-added to teams in the new org.
8. Invalidates **GitHub Apps installations** that were scoped to the source org.
9. **Does not** transfer Actions usage minutes counters.

---

## Pre-Transfer Audit Checklist

Run this before initiating the transfer:

```bash
#!/usr/bin/env bash
# scripts/pre-transfer-audit.sh
# Usage: GITHUB_TOKEN=xxx REPO=owner/repo bash pre-transfer-audit.sh

REPO="${REPO:?set REPO=owner/repo}"
API="https://api.github.com/repos/${REPO}"
AUTH="Authorization: Bearer ${GITHUB_TOKEN:?set GITHUB_TOKEN}"

echo "=== Deploy Keys ==="
gh api "/repos/${REPO}/keys" --jq '.[].title'

echo "=== Actions Secrets ==="
gh api "/repos/${REPO}/actions/secrets" --jq '.secrets[].name'

echo "=== Dependabot Secrets ==="
gh api "/repos/${REPO}/dependabot/secrets" --jq '.secrets[].name'

echo "=== Variables ==="
gh api "/repos/${REPO}/actions/variables" --jq '.variables[].name'

echo "=== Environments ==="
gh api "/repos/${REPO}/environments" \
  --jq '.environments[] | {name, protection_rules: [.protection_rules[].type]}'

echo "=== Branch Protection Rules ==="
gh api "/repos/${REPO}/branches" --jq '.[].name' | while read branch; do
  PROTECTED=$(gh api "/repos/${REPO}/branches/${branch}" --jq '.protected')
  if [ "$PROTECTED" = "true" ]; then
    echo "  protected: $branch"
  fi
done

echo "=== GitHub Apps with repo access ==="
gh api "/repos/${REPO}/installation" --jq '.app_slug // "none"' 2>/dev/null || echo "none"

echo "=== Webhooks ==="
gh api "/repos/${REPO}/hooks" --jq '.[].config.url'

echo "=== Collaborators (outside org) ==="
gh api "/repos/${REPO}/collaborators?affiliation=outside" --jq '.[].login'
```

---

## Secrets Inventory — Export Before Transfer

Secrets cannot be read back after creation (only overwritten). Before
transferring, ensure all secret **names and their source** are documented:

```typescript
// scripts/export-secret-inventory.ts
// Exports secret names only (values are never readable via API)
import { Octokit } from "@octokit/rest";

const octokit = new Octokit({ auth: process.env.GITHUB_TOKEN });
const [owner, repo] = (process.env.REPO ?? "").split("/");

const { data: secrets } = await octokit.rest.actions.listRepoSecrets({
  owner,
  repo,
  per_page: 100,
});

const { data: vars } = await octokit.rest.actions.listRepoVariables({
  owner,
  repo,
  per_page: 100,
});

const { data: depSecrets } =
  await octokit.rest.dependabot.listRepoSecrets({
    owner,
    repo,
    per_page: 100,
  });

const inventory = {
  repo: `${owner}/${repo}`,
  exportedAt: new Date().toISOString(),
  actionSecrets: secrets.secrets.map((s) => ({
    name: s.name,
    createdAt: s.created_at,
    updatedAt: s.updated_at,
  })),
  actionVariables: vars.variables.map((v) => ({
    name: v.name,
    value: v.value, // variables ARE readable
  })),
  dependabotSecrets: depSecrets.secrets.map((s) => ({
    name: s.name,
    createdAt: s.created_at,
  })),
};

console.log(JSON.stringify(inventory, null, 2));
```

Store output in 1Password or your secrets manager, not in git.

---

## Transfer Execution

```bash
# Via gh CLI (requires admin on both source and target)
gh api --method POST \
  /repos/source-owner/example project-monorepo/transfer \
  -f new_owner="your-org" \
  -F team_ids[]="12345"   # optional: add to team immediately

# Confirm the new URL
gh api /repos/your-org/example project-monorepo --jq '.full_name'
```

The transfer is **instantaneous** for the owner change but may take up to 30
seconds before GitHub Actions workflows reflect the new org context.

---

## Post-Transfer Hardening Checklist

```bash
#!/usr/bin/env bash
# scripts/post-transfer-harden.sh
NEW_REPO="your-org/example project-monorepo"

echo "1. Re-add to teams"
gh api --method PUT \
  /orgs/your-org/teams/platform-leads/repos/${NEW_REPO} \
  -f permission="push"

echo "2. Restore branch protection / rulesets"
# Rulesets scoped to the org may auto-apply; check:
gh api /repos/${NEW_REPO}/rulesets --jq '.[].name'

echo "3. Re-create deploy keys"
# Generate new SSH key pair, register public key
gh api --method POST /repos/${NEW_REPO}/keys \
  -f title="ci-deploy-key-2026" \
  -f key="$(cat ~/.ssh/ci_deploy_key.pub)" \
  -F read_only=true

echo "4. Re-create Actions secrets"
# Add secrets one by one (values retrieved from 1Password)
gh secret set CF_API_TOKEN --repo="${NEW_REPO}" --body="$(op read op://Engineering/CF_API_TOKEN/credential)"
gh secret set CF_ACCOUNT_ID --repo="${NEW_REPO}" --body="$(op read op://Engineering/CF_ACCOUNT_ID/credential)"

echo "5. Re-create Dependabot secrets"
gh secret set NPM_TOKEN --repo="${NEW_REPO}" --app=dependabot --body="$(op read op://Engineering/NPM_TOKEN/credential)"

echo "6. Update environment protection rules"
gh api --method PUT /repos/${NEW_REPO}/environments/production \
  -f 'reviewers[0][type]=Team' \
  -F 'reviewers[0][id]=12345'

echo "7. Verify GitHub App installation"
gh api /repos/${NEW_REPO}/installation --jq '{app_slug, id}'

echo "8. Update webhooks to new URL if org-specific"
gh api /repos/${NEW_REPO}/hooks --jq '.[].config.url'
```

---

## Updating CI References to the Old URL

Search for hardcoded `old-owner/example project-monorepo` references:

```bash
# Find references in workflow files
grep -r "old-owner/example project-monorepo" .github/workflows/ --include="*.yml"

# Find references in Wrangler configs
grep -r "old-owner" workers/ --include="wrangler*.toml"

# Find references in package.json repository fields
grep -r '"repository"' . --include="package.json" | grep "old-owner"
```

Update all references and push before the redirect expires:

```bash
# Bulk replace in workflow files
find .github -name "*.yml" -exec \
  sed -i 's|old-owner/example project-monorepo|your-org/example project-monorepo|g' {} +
```

---

## GitHub Apps Re-authorisation

If the repository had a GitHub App installed (e.g. the example project CI app), the
installation needs to be granted access to the repository in its new location:

```bash
# List App installations the org has
gh api /orgs/your-org/installations --jq '.installations[].app_slug'

# Grant the app access to the transferred repo
gh api --method PUT \
  /user/installations/<installation_id>/repositories/<repo_id>
```

For Apps using OIDC (no stored tokens), re-verify the OIDC subject claim
matches the new repo path — the subject is usually
`repo:your-org/example project-monorepo:ref:refs/heads/main` and must be updated in
Cloudflare's identity provider config.

---

## Cloudflare OIDC Subject Update

```bash
# Update the allowed subject in CF Workers Tokens
# Old subject: repo:old-owner/example project-monorepo:environment:production
# New subject: repo:your-org/example project-monorepo:environment:production

# Verify current OIDC token subjects in CF (via Terraform or dashboard)
# Cloudflare Workers Tokens → Edit → Subject conditions
```

---

## Anti-patterns

- **Transferring without a pre-audit**: you discover missing secrets only when
  CI breaks in production. Always run the audit script first.
- **Relying on the URL redirect indefinitely**: GitHub's redirect lasts up to
  1 year but is not guaranteed. Update all references within 30 days.
- **Assuming rulesets transfer**: organisation-level rulesets may auto-apply but
  repository-level rulesets do not transfer. Verify after the move.
- **Transferring with external collaborators still on the repo**: outside
  collaborators lose access on transfer. Notify them and re-grant if needed.
- **Not rotating secrets after transfer**: even though the values are not
  exposed, a transfer is a good trigger to rotate long-lived tokens and delete
  any that are no longer needed.

---

## Gotchas

- GitHub audit log entries for events that happened before the transfer still
  show the old repo path. Queries filtered by the new path will miss pre-transfer
  history.
- `GITHUB_REPOSITORY` in Actions workflows updates immediately after transfer.
  Any workflow that caches the repo name in a Cloudflare KV key or D1 row will
  have stale data.
- If the repo used GitHub Packages (npm or container registry), the package
  namespace changes from `old-owner/package` to `your-org/package`. This breaks
  consumers pinned to the old registry URL.
- Dependabot is automatically **disabled** after transfer and must be re-enabled
  in the Security tab of the new location.
- The `Transfer repository` UI button is only available to admins. For org-to-
  org transfers, an admin on _both_ sides must confirm via email link.

---

## Verification

```bash
# 1. Confirm new URL resolves correctly
gh api /repos/your-org/example project-monorepo --jq '.full_name, .html_url'

# 2. Confirm old URL redirects
curl -I https://github.com/old-owner/example project-monorepo | grep -i location

# 3. Trigger a CI run to verify secrets and Actions work
gh workflow run ci.yml --repo your-org/example project-monorepo --ref main

# 4. Confirm Dependabot is enabled
gh api /repos/your-org/example project-monorepo \
  --jq '{security_updates: .security_and_analysis.dependabot_security_updates.status}'
```

---

## Related

- `github-actions-secrets-management.md`
- `github-apps-installation-tokens.md`
- `github-actions-oidc-cloudflare.md`
- `github-organization-settings.md`
- `github-repository-archiving-policy.md`

---

## Sources

- GitHub Docs — Transferring a repository: https://docs.github.com/en/repositories/creating-and-managing-repositories/transferring-a-repository
- GitHub Docs — Transfer repository API: https://docs.github.com/en/rest/repos/repos#transfer-a-repository
- GitHub Docs — About GitHub Apps: https://docs.github.com/en/apps/overview
- Cloudflare Docs — OIDC subject claims: https://developers.cloudflare.com/cloudflare-one/identity/idp-integration/github/
