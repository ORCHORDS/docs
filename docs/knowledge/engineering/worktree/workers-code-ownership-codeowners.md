# CODEOWNERS for Workers Monorepos

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

PRs touching the `payments/` Worker merge without a review from the security team. Knowledge base articles get merged without a technical writer review. Changes to shared `@example-org/example-repo` go live without the platform team sign-off. GitHub's CODEOWNERS file solves this by automatically requesting reviews from the right people whenever files in their domain are touched — and can be configured as a required check so PRs cannot merge without those reviews.

## Context

GitHub reads `.github/CODEOWNERS` (or `CODEOWNERS` at root, or `docs/CODEOWNERS`) on every PR. For each file changed in the PR, GitHub matches it against CODEOWNERS patterns (last match wins) and requests a review from the matched owner. Combined with branch protection's "Require review from Code Owners" setting, these reviews become blocking. Owners can be GitHub usernames, team slugs (`@org/team`), or email addresses. In a Workers monorepo, ownership maps naturally to directory boundaries.

## Solution

**`.github/CODEOWNERS`** — full monorepo ownership map:

```
# ============================================================
# CODEOWNERS — orchords monorepo
# https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
#
# Rules: last matching pattern wins.
# Blank lines and lines starting with # are ignored.
# ============================================================

# --- Default owner (fallback for all files not matched below)
*                               @example-org/example-repo

# --- Repository configuration — platform team only
/.github/                       @example-org/example-repo
/renovate.json                  @example-org/example-repo
/turbo.json                     @example-org/example-repo
/.husky/                        @example-org/example-repo

# --- Shared packages
/packages/types/                @example-org/example-repo
/packages/utils/                @example-org/example-repo
/packages/middleware/           @example-org/example-repo @example-org/example-repo

# --- Workers — platform team owns all Workers by default
/workers/                       @example-org/example-repo

# --- API Gateway — platform team
/workers/api-gateway/           @example-org/example-repo

# --- Auth Worker — platform + security must both review
/workers/auth/                  @example-org/example-repo @example-org/example-repo

# --- Payments Worker — platform + security + payments team required
/workers/payments/              @example-org/example-repo @example-org/example-repo @example-org/example-repo

# --- Notifications Worker — platform team
/workers/notifications/         @example-org/example-repo

# --- Security-sensitive paths — security team regardless of Worker
/workers/**/security/           @example-org/example-repo
/workers/**/auth/               @example-org/example-repo
/packages/middleware/src/auth*  @example-org/example-repo

# --- Database migrations — platform + DBA review
/migrations/                    @example-org/example-repo @example-org/example-repo

# --- Knowledge base — technical writers
/documentation/                @example-org/example-repo
/documentation/docs/policies/worktree/       @example-org/example-repo @example-org/example-repo

# --- CI/CD pipelines — platform team
/.github/workflows/             @example-org/example-repo

# --- Infrastructure as Code
/infra/                         @example-org/example-repo @example-org/example-repo

# --- Secrets and environment configuration
/.env.example                   @example-org/example-repo @example-org/example-repo
/workers/**/.dev.vars.example   @example-org/example-repo @example-org/example-repo
```

**Branch protection configuration (via GitHub REST API / Terraform):**

```bash
# Enable required CODEOWNERS review on main branch
gh api repos/example-org/example-repo/branches/main/protection \
  --method PUT \
  --field required_status_checks=null \
  --field enforce_admins=true \
  --field required_pull_request_reviews='{"require_code_owner_reviews":true,"required_approving_review_count":1,"dismiss_stale_reviews":true}' \
  --field restrictions=null
```

**Terraform equivalent (`infra/github/branch_protection.tf`):**

```hcl
resource "github_branch_protection" "main" {
  repository_id = github_repository.workers_monorepo.node_id
  pattern       = "main"
  enforce_admins = true

  required_pull_request_reviews {
    required_approving_review_count = 1
    require_code_owner_reviews      = true
    dismiss_stale_reviews           = true
    restrict_dismissals             = false
  }

  required_status_checks {
    strict   = true
    contexts = [
      "CI / typecheck",
      "CI / lint",
      "CI / test",
      "CI / wrangler-dry-run",
    ]
  }
}
```

**CODEOWNERS linting in CI (`.github/workflows/codeowners-lint.yml`):**

```yaml
name: CODEOWNERS Lint

on:
  pull_request:
    paths:
      - '.github/CODEOWNERS'

jobs:
  lint-codeowners:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Validate CODEOWNERS syntax
        uses: mszostok/codeowners-validator@v0.7.4
        with:
          checks: "files,owners,duppatterns,syntax"
          owner_checker_repository: ${{ github.repository }}
        env:
          GITHUB_ACCESS_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**`codeowners-validator` checks explained:**

| Check | What it validates |
|---|---|
| `files` | Every path pattern in CODEOWNERS matches at least one real file in the repo |
| `owners` | Every `@org/team` or `@username` exists in the GitHub organization |
| `duppatterns` | No duplicate or shadowed patterns |
| `syntax` | CODEOWNERS file is syntactically valid |

**TypeScript script to audit effective ownership of a path:**

```typescript
import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

interface OwnerRule {
  pattern: string;
  owners: string[];
  lineNumber: number;
}

function parseCodeowners(filePath: string): OwnerRule[] {
  const lines = fs.readFileSync(filePath, 'utf-8').split('\n');
  const rules: OwnerRule[] = [];

  lines.forEach((line, idx) => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) return;

    const parts = trimmed.split(/\s+/);
    const pattern = parts[0];
    const owners = parts.slice(1);

    rules.push({ pattern, owners, lineNumber: idx + 1 });
  });

  return rules;
}

function matchesPattern(filePath: string, pattern: string): boolean {
  // Simplified matcher — real implementation uses minimatch or similar
  const normalized = pattern.replace(/^\//, '');
  if (normalized.endsWith('/')) {
    return filePath.startsWith(normalized);
  }
  if (normalized.startsWith('**/')) {
    return filePath.includes(normalized.slice(3));
  }
  return filePath === normalized || filePath.startsWith(normalized + '/');
}

function getEffectiveOwners(targetPath: string, rules: OwnerRule[]): OwnerRule | null {
  let lastMatch: OwnerRule | null = null;

  for (const rule of rules) {
    if (matchesPattern(targetPath, rule.pattern)) {
      lastMatch = rule;
    }
  }

  return lastMatch;
}

// Usage
const codeownersPath = path.resolve('.github/CODEOWNERS');
const rules = parseCodeowners(codeownersPath);

const testPaths = [
  'workers/payments/src/index.ts',
  'documentation/docs/policies/worktree/example.md',
  'migrations/0010_worker_releases.sql',
  'workers/auth/security/jwt.ts',
];

for (const p of testPaths) {
  const match = getEffectiveOwners(p, rules);
  console.log(`${p}:`);
  console.log(`  owners: ${match?.owners.join(', ') ?? '(none)'}`);
  console.log(`  rule: line ${match?.lineNumber ?? 'N/A'}: ${match?.pattern ?? '(no match)'}`);
  console.log();
}
```

**GitHub CLI: verify which teams own a specific file:**

```bash
# List owners of a specific file on main
gh api repos/example-org/example-repo/codeowners/errors

# Simulate CODEOWNERS match for a file path (undocumented but useful endpoint)
gh api "repos/example-org/example-repo/contents/.github/CODEOWNERS" \
  --jq '.content' | base64 -d | grep 'payments'

# Check PR reviews requested by CODEOWNERS
gh pr view <PR_NUMBER> --json reviewRequests \
  --jq '.reviewRequests[] | .login // .name'
```

## Implementation Details

- GitHub evaluates CODEOWNERS patterns in order and the **last** matching pattern wins. The wildcard `*` at the top sets a default owner, but more specific rules below it override it for their paths. A `payments/` rule below `workers/` overrides the general Workers ownership.
- Team ownership (`@example-org/example-repo`) is preferable to individual ownership (`@bob`) because team membership changes over time without requiring CODEOWNERS updates. Teams also allow GitHub to pick any available member for the review.
- `"dismiss_stale_reviews": true` in branch protection invalidates existing CODEOWNER approvals when new commits are pushed to the PR branch. This prevents approving a safe version and then sneaking in a change.
- The CODEOWNERS file itself should be owned by `@example-org/example-repo` (via the `/.github/` rule). This means changing ownership rules also requires platform team approval — preventing anyone from removing their own required reviewers.

## Anti-patterns

- **Individual usernames instead of team slugs**: When the owner leaves the org, GitHub silently removes the review requirement. Use `@org/team` slugs so membership is managed in GitHub Teams.
- **Overly broad patterns that match too much**: A pattern like `*.ts` matches every TypeScript file in the repo, adding a review requirement to every PR. Scope patterns to directories.
- **Not enabling "Require review from Code Owners" in branch protection**: Without this setting, CODEOWNERS still requests reviews but they are not required — PRs can merge without them.
- **Listing nonexistent teams**: If `@example-org/example-repo` does not exist as a GitHub Team in the `orchords` org, GitHub silently ignores the ownership rule. Use `codeowners-validator` to catch this in CI.

## Gotchas

- CODEOWNERS only triggers review requests on files **changed** in the PR. If a PR changes `workers/payments/src/index.ts`, only the `payments` pattern matches — not parent directory rules that were previously satisfied by a different PR.
- GitHub enforces a maximum of 100 owner entries per CODEOWNERS line. For a pattern that requires many teams, create an intermediary GitHub Team that contains the member teams.
- `codeowners-validator`'s `files` check requires the full repository to be checked out. In a monorepo with many large generated files, add `sparse-checkout` or accept that the `files` check will only validate against a subset of paths.
- CODEOWNERS is case-insensitive on case-insensitive file systems (macOS), but case-sensitive on Linux (where GitHub Actions runs). Keep path capitalisation consistent with the actual directory names.
- Draft PRs do not trigger CODEOWNERS review requests. Reviews are only auto-requested when a PR is opened or converted from draft to ready-for-review.

## Verification

```bash
# Validate CODEOWNERS syntax locally
npx --package @github/codeowners-validator -- codeowners-validator \
  --owner orchords \
  --repository workers-monorepo \
  --github-token "$GITHUB_TOKEN"

# Open a test PR touching payments/ and confirm review is requested
gh pr create \
  --title "test: codeowners validation" \
  --body "Testing CODEOWNERS review requests" \
  --base main \
  --head test/codeowners-check

# Verify review requests were added
gh pr view --json reviewRequests \
  --jq '[.reviewRequests[] | .login // .name]'
# Expected: includes example-org/example-repo, example-org/example-repo, example-org/example-repo

# Check branch protection is configured correctly
gh api repos/example-org/example-repo/branches/main/protection \
  --jq '.required_pull_request_reviews.require_code_owner_reviews'
# Expected: true
```

## Related

- `workers-monorepo-turborepo-setup.md` — directory structure that CODEOWNERS patterns map to
- `workers-git-hooks-husky-setup.md` — local enforcement before CODEOWNERS remote enforcement
- `merge-queue-github-actions.md` — merge queue enforces CODEOWNER approval before queuing
- `trunk-based-development-workflow.md` — branch protection that requires CODEOWNER reviews

## Sources

- https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
- https://github.com/mszostok/codeowners-validator
- https://docs.github.com/en/rest/branches/branch-protection
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
