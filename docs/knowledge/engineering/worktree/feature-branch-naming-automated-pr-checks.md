# Feature Branch Naming Conventions and Automated PR Checks

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

---

## Symptom / Use-case

Branch names in the repository are inconsistent: `fix-login`, `ORCH-112`, `johns-stuff`,
`test123`, and `feat/user-auth-2` all coexist. Pull requests that arrive with opaque names
make triage harder, break automation that relies on branch name patterns (auto-labeling,
release note generation, environment routing), and cause problems for bots that parse ticket
references. You need a single enforced convention, documented in one place, checked
automatically on every PR open/re-open, and enforced as a required status check before merge.

---

## Context

Branch naming conventions serve more than aesthetics. In a Cloudflare Workers monorepo they
gate several automated behaviors:

- **Preview environment routing**: Wrangler can deploy to a named preview environment derived
  from the branch name. A branch named `feat/ORCH-112-user-auth` maps cleanly to a preview
  URL; `johns-stuff` does not.
- **Auto-labeling**: GitHub Actions labels PRs automatically based on branch prefix
  (`feat/` → `feature`, `fix/` → `bug`, `chore/` → `chore`). Inconsistent names bypass
  labeling and require manual triage.
- **Changelog grouping**: `release-please` and `semantic-release` parse branch names or
  commit types to group changelog entries. Unlabeled PRs appear under "Uncategorized."
- **Ticket linking**: `ORCH-NNNN` in the branch name is parsed by Jira smart commits and
  GitHub branch integrations to auto-link work items.

The convention below is a practical middle ground: strict enough for automation, loose enough
for exploratory and hotfix branches.

---

## Branch Naming Convention

### Pattern

```
<type>/<ticket>-<short-description>
```

| Segment | Required | Values | Notes |
|---------|----------|--------|-------|
| `<type>` | Yes | `feat`, `fix`, `chore`, `refactor`, `docs`, `test`, `release`, `hotfix` | Maps to conventional commit types |
| `/` | Yes | — | Separator; never a hyphen or underscore |
| `<ticket>` | Conditional | `ORCH-NNNN` | Required for `feat`, `fix`, `refactor`; optional for `chore`, `docs`, `test` |
| `-` | Yes | — | Separator after ticket number |
| `<short-description>` | Yes | `[a-z0-9-]+` | Lowercase, hyphens only, 3–50 characters |

### Valid examples

```
feat/ORCH-412-user-auth-oauth
fix/ORCH-501-race-condition-r2-upload
chore/update-wrangler-deps
docs/ORCH-300-api-versioning-guide
hotfix/ORCH-555-rate-limiter-bypass
refactor/ORCH-210-d1-query-abstraction
test/unit-tests-kv-cache-layer
release/v2.1.0
```

### Invalid examples

```
feature/user-auth          # wrong type prefix (should be 'feat')
ORCH-412                   # missing type and description
john/my-changes            # personal namespace not in allowed types
Fix-Bug-123                # uppercase, wrong separator
feat_ORCH-412_user_auth    # underscores instead of hyphens and slashes
```

---

## Regex Reference

```
^(feat|fix|chore|refactor|docs|test|release|hotfix)\/(([A-Z]+-[0-9]+)-)?[a-z0-9][a-z0-9-]{2,49}$
```

- Ticket segment (`([A-Z]+-[0-9]+)-`) is optional (the outer `(...)?` wrapper).
- Description must start with a lowercase letter or digit.
- Total description length: 3–50 characters (enforced by `{2,49}` after the required first char).
- Allows any project prefix (`ORCH`, `PLT`, `INF`), not just `ORCH`.

---

## Automated PR Check: GitHub Actions

```yaml
# .github/workflows/branch-name-check.yml
name: Branch Name Convention

on:
  pull_request:
    types: [opened, reopened, synchronize, edited]

permissions:
  pull-requests: write
  statuses: write

jobs:
  check-branch-name:
    runs-on: ubuntu-latest

    steps:
      - name: Validate branch name
        id: validate
        env:
          BRANCH: ${{ github.head_ref }}
        run: |
          PATTERN='^(feat|fix|chore|refactor|docs|test|release|hotfix)\/(([A-Z]+-[0-9]+)-)?[a-z0-9][a-z0-9-]{2,49}$'

          if echo "$BRANCH" | grep -qP "$PATTERN"; then
            echo "valid=true"  >> "$GITHUB_OUTPUT"
            echo "Branch name '$BRANCH' is valid."
          else
            echo "valid=false" >> "$GITHUB_OUTPUT"
            echo "::error::Branch name '$BRANCH' does not match the required convention."
            echo "::error::Expected pattern: <type>/<ticket>-<description>"
            echo "::error::Examples: feat/ORCH-100-add-auth, fix/race-condition, chore/deps"
          fi

      - name: Post PR comment on failure
        if: steps.validate.outputs.valid == 'false'
        uses: actions/github-script@v7
        with:
          script: |
            const branch = '${{ github.head_ref }}';
            const body = [
              '## Branch Name Convention Failure',
              '',
              `Branch \`${branch}\` does not match the required naming convention.`,
              '',
              '**Required pattern**: `<type>/<ticket>-<description>`',
              '',
              '| Segment | Valid values |',
              '|---------|--------------|',
              '| `type`  | `feat`, `fix`, `chore`, `refactor`, `docs`, `test`, `release`, `hotfix` |',
              '| `ticket` | `ORCH-NNN` (required for feat/fix/refactor) |',
              '| `description` | lowercase, hyphens only, 3–50 chars |',
              '',
              '**Valid examples**:',
              '- `feat/ORCH-412-user-auth-oauth`',
              '- `fix/ORCH-501-race-condition-r2`',
              '- `chore/update-wrangler-deps`',
              '',
              'Please rename your branch and re-open the PR, or push a new branch with the correct name.',
            ].join('\n');

            // Only post if no matching comment already exists
            const comments = await github.rest.issues.listComments({
              ...context.repo,
              issue_number: context.payload.pull_request.number,
            });
            const alreadyPosted = comments.data.some(c =>
              c.body.includes('Branch Name Convention Failure'));
            if (!alreadyPosted) {
              await github.rest.issues.createComment({
                ...context.repo,
                issue_number: context.payload.pull_request.number,
                body,
              });
            }

      - name: Fail on invalid branch name
        if: steps.validate.outputs.valid == 'false'
        run: exit 1
```

---

## Auto-labeling Based on Branch Type

```yaml
# .github/workflows/auto-label.yml
name: Auto Label PR

on:
  pull_request:
    types: [opened, reopened]

permissions:
  pull-requests: write

jobs:
  label:
    runs-on: ubuntu-latest
    steps:
      - name: Apply label
        uses: actions/github-script@v7
        with:
          script: |
            const branch = '${{ github.head_ref }}';
            const labelMap = {
              feat:     'feature',
              fix:      'bug',
              chore:    'chore',
              refactor: 'refactor',
              docs:     'documentation',
              test:     'test',
              release:  'release',
              hotfix:   'hotfix',
            };

            const type = branch.split('/')[0];
            const label = labelMap[type];
            if (!label) return;

            // Ensure label exists
            try {
              await github.rest.issues.getLabel({
                ...context.repo,
                name: label,
              });
            } catch {
              await github.rest.issues.createLabel({
                ...context.repo,
                name: label,
                color: ({ feature: '0075ca', bug: 'd73a4a', chore: 'cfd3d7',
                           refactor: 'e4e669', documentation: '0052cc',
                           test: '5319e7', release: '006b75', hotfix: 'b60205' })[label] ?? 'cccccc',
              });
            }

            await github.rest.issues.addLabels({
              ...context.repo,
              issue_number: context.payload.pull_request.number,
              labels: [label],
            });
```

---

## Linking Ticket References to Jira / GitHub Projects

When the branch contains a ticket reference, the PR description should also include it.
Enforce this with a second check:

```yaml
- name: Ensure ticket link in PR body
  uses: actions/github-script@v7
  with:
    script: |
      const branch = '${{ github.head_ref }}';
      const body   = context.payload.pull_request.body ?? '';

      const ticketMatch = branch.match(/\/([A-Z]+-\d+)-/);
      if (!ticketMatch) return;                     // no ticket in branch name

      const ticket = ticketMatch[1];               // e.g. ORCH-412
      if (!body.includes(ticket)) {
        core.setFailed(
          `PR body must reference the ticket ${ticket} found in the branch name.`
        );
      }
```

---

## Renaming a Branch After PR Is Open

GitHub does not allow renaming a branch via the web UI after a PR is open without closing
the PR. The correct sequence:

```bash
# 1. Create the correctly named branch from the current one
git checkout -b feat/ORCH-412-user-auth-oauth

# 2. Push the new branch
git push origin feat/ORCH-412-user-auth-oauth

# 3. Update the PR's base branch via gh CLI (keep PR open)
gh pr edit <PR_NUMBER> --base main   # ensure base is correct
# GitHub will automatically update the PR to track the new branch
# if you close the old one and open a new PR pointing to the new branch.

# 4. Delete the old branch
git push origin --delete bad-branch-name
```

The cleanest path is always to name the branch correctly before the first push.

---

## Anti-patterns

- **Using personal namespaces** (`john/feature-x`): personal prefixes are not in the allowed
  type list, making automation impossible and requiring manual disambiguation.
- **Long ticket-only branches** (`ORCH-412`): these fail the required description segment,
  leave git-log entries context-free, and make `git branch -r` unusable at a glance.
- **CamelCase or snake_case**: mixed case branches break shell pattern-matching and fail the
  lowercase-only description requirement. Lowercase hyphens are universally portable.
- **Skipping the ticket for feat/fix branches**: the ticket number is the primary audit trail
  between code and planned work. Waiving it "just this once" erodes the policy incrementally.
- **Making the branch-name check advisory (non-blocking)**: if the check is not a required
  status on the branch protection rule, developers will ignore failures.

---

## Gotchas

- **Dependabot and Renovate branches**: dependency update bots create branches like
  `dependabot/npm_and_yarn/wrangler-3.80.0`. These must be explicitly exempted from the
  naming check. Add a condition: `if: !startsWith(github.head_ref, 'dependabot/') &&
  !startsWith(github.head_ref, 'renovate/')`.
- **Release Please branches**: `release-please--branches--main--components--*` must also be
  exempted. Check for `startsWith(github.head_ref, 'release-please--')`.
- **`grep -P` (Perl regex) may not be available** on some minimal GitHub Actions runners.
  Use `grep -E` with a POSIX-compatible pattern, or call Node.js for the regex test.
- **Branch protection and required status checks**: the workflow name and job name must
  exactly match what is configured in the branch protection rule settings. A renamed job
  silently breaks the required-check enforcement.

---

## Verification

```bash
# Test the regex locally against your branch name
BRANCH="feat/ORCH-412-user-auth-oauth"
echo "$BRANCH" | grep -P \
  '^(feat|fix|chore|refactor|docs|test|release|hotfix)\/(([A-Z]+-[0-9]+)-)?[a-z0-9][a-z0-9-]{2,49}$' \
  && echo "VALID" || echo "INVALID"

# List all remote branches that fail the convention
git fetch --prune
git for-each-ref --format='%(refname:short)' refs/remotes/origin/ | \
  sed 's|^origin/||' | \
  grep -vP '^(feat|fix|chore|refactor|docs|test|release|hotfix)\/' | \
  grep -v '^(main|master|production|staging|HEAD|dependabot|renovate|release-please)'

# Check which PRs lack a label (symptom of bypassed auto-labeling)
gh pr list --limit 50 --json number,headRefName,labels \
  --jq '.[] | select(.labels | length == 0) | "\(.number) \(.headRefName)"'
```

---

## Related

- `branch-strategies-2026.md` — overall branching model and lifetime policies
- `conventional-commits-2026.md` — commit message types that mirror branch prefixes
- `pr-templates-2026.md` — PR description templates and ticket reference requirements
- `stale-branch-cleanup-github-actions.md` — automated removal of old branches
- `trunk-based-development-2026.md` — short-lived branch lifecycle

---

## Sources

- GitHub Actions: `pull_request` event types and `head_ref` context
- `actions/github-script` — https://github.com/actions/github-script
- Conventional Commits specification — https://www.conventionalcommits.org
- Jira Smart Commits branch integration — https://support.atlassian.com/jira-software-cloud/docs/process-issues-with-smart-commits/
- Release Please branch naming — https://github.com/googleapis/release-please
