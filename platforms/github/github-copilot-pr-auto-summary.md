# GitHub Copilot Auto-Generated PR Descriptions and Summaries

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Engineers open PRs with empty or one-line descriptions, forcing reviewers to read every
diff to understand intent.  Copilot's PR summary feature generates a structured
description from the diff and commit messages, reducing review prep time and ensuring
consistent PR documentation across the team.

## Context

GitHub Copilot can generate PR descriptions in two modes:

1. **In-IDE (VS Code / JetBrains)** — the Copilot panel in the PR creation flow offers
   a "Generate description" button powered by the diff context.
2. **GitHub.com UI** — the "Copilot" icon in the PR description textarea calls the same
   model server-side; available to repos with an active Copilot for Business or
   Enterprise seat.
3. **Copilot coding agent / GitHub Actions** — the `gh copilot suggest` CLI and the
   Copilot API (preview) enable programmatic summary generation in CI workflows.

Auto-summaries work best when commit messages follow Conventional Commits; they extract
the `feat:`, `fix:`, `chore:` prefixes to build structured change lists.

---

## 1. Enabling Copilot PR Summaries in the GitHub UI

Copilot PR summaries are on by default for organisations with Copilot for Business.
To confirm the policy:

```bash
# Check org-level Copilot policy (requires org admin or billing manager)
gh api orgs/{org}/copilot/billing \
  | jq '{seat_breakdown, public_code_suggestions, ide_chat, platform_chat}'
```

In the GitHub.com PR creation page:
1. Open the **Description** textarea.
2. Click the **Copilot icon** (sparkle) in the toolbar.
3. Select **"Summarize changes"**.

The model produces a markdown description using:
- Commit subject lines
- File-level change summary (file names + hunks)
- Test file additions/removals

---

## 2. PR Template Integration

Copilot's summary fills in *around* your existing PR template rather than replacing it.
Structure the template to guide the summary:

```markdown
<!-- .github/pull_request_template.md -->
## Summary
<!-- Copilot: summarize the diff here -->

## Type of change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Chore / refactor

## Test plan
<!-- Copilot: list tests added or modified -->

## Screenshots / recordings
<!-- Add if UI changes are included -->

## Checklist
- [ ] Tests pass locally
- [ ] Docs updated if public API changed
- [ ] Dependent PRs linked above
```

Copilot will populate `## Summary` and `## Test plan` sections when it detects the
section headings.

---

## 3. Programmatic Summary via Copilot CLI in Actions

Use `gh copilot explain` or the Copilot API to post a summary comment automatically
when a PR is opened.

```yaml
# .github/workflows/copilot-pr-summary.yml
name: Copilot PR Summary

on:
  pull_request:
    types: [opened]

permissions:
  pull-requests: write
  contents: read

jobs:
  summarize:
    runs-on: ubuntu-latest
    # Only run if Copilot is licensed; skip forks to avoid secret exposure
    if: github.event.pull_request.head.repo.full_name == github.repository
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Generate diff summary
        id: summary
        run: |
          DIFF=$(git diff origin/${{ github.base_ref }}...HEAD --stat)
          COMMITS=$(git log origin/${{ github.base_ref }}..HEAD --oneline)
          cat <<EOF > /tmp/summary_input.txt
          Commits:
          $COMMITS

          File changes:
          $DIFF
          EOF
          echo "input_file=/tmp/summary_input.txt" >> "$GITHUB_OUTPUT"

      - name: Post summary comment via GitHub Script
        uses: actions/github-script@v7
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          script: |
            const fs = require('fs');
            const input = fs.readFileSync('/tmp/summary_input.txt', 'utf8');
            // In production, call the Copilot API or a Workers endpoint
            // that wraps Claude / Copilot to generate the prose summary.
            // Here we post the raw diff-stat as a baseline.
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.payload.pull_request.number,
              body: `## Auto-summary (Copilot)\n\n\`\`\`\n${input}\`\`\``
            });
```

---

## 4. Copilot API Programmatic Summary (Preview)

The Copilot API (currently in private preview) exposes a `/copilot/chat/completions`
endpoint that accepts GitHub context.  For organisations in the preview:

```typescript
// workers/copilot-summary/src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { prNumber, repo, owner } = await request.json<{
      prNumber: number;
      repo: string;
      owner: string;
    }>();

    const diffRes = await fetch(
      `https://api.github.com/repos/${owner}/${repo}/pulls/${prNumber}`,
      {
        headers: {
          Authorization: `token ${env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github.diff",
        },
      }
    );
    const diff = await diffRes.text();

    const copilotRes = await fetch(
      "https://api.githubcopilot.com/chat/completions",
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.COPILOT_TOKEN}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model: "gpt-4o",
          messages: [
            {
              role: "system",
              content:
                "You are a senior engineer. Summarise this PR diff in under 200 words " +
                "using markdown bullet points. Group by feature area.",
            },
            { role: "user", content: diff.slice(0, 12_000) },
          ],
        }),
      }
    );

    const { choices } = await copilotRes.json<{ choices: { message: { content: string } }[] }>();
    return Response.json({ summary: choices[0].message.content });
  },
};
```

---

## 5. Org Policy: Require Non-Empty PR Descriptions

Combine Copilot summaries with a required-check that validates description length to
prevent blank PRs from merging.

```yaml
# .github/workflows/pr-description-check.yml
name: PR Description Check

on:
  pull_request:
    types: [opened, edited, synchronize]

jobs:
  check-description:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/github-script@v7
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          script: |
            const body = context.payload.pull_request.body ?? '';
            if (body.trim().length < 50) {
              core.setFailed(
                'PR description is too short (< 50 chars). ' +
                'Use the Copilot summary button or write a description.'
              );
            }
```

---

## Anti-patterns

- Accepting the raw Copilot summary without review — treat it as a first draft; the
  model can misattribute intent when commit messages are vague.
- Using Copilot summaries as a substitute for a PR template — the template enforces
  reviewer-specific sections (test plan, screenshots) that the model won't add.
- Posting summaries as GitHub Actions bot comments on every synchronize event — this
  floods the PR timeline; trigger only on `opened` or add a `/summarize` slash command.
- Storing Copilot API tokens in repository secrets without rotation; use a GitHub App
  installation token with minimum scopes instead.

## Gotchas

- The Copilot PR summary in the GitHub UI is not available for private repos on free
  plans; it requires Copilot for Business or Enterprise.
- `gh copilot suggest` is a CLI assistant, not a programmatic API — it is interactive
  and cannot be piped cleanly in CI; use the API or GitHub Models instead.
- Diffs larger than ~30 000 tokens are silently truncated; for very large PRs the
  summary will be incomplete — split large PRs or summarise per-file.
- Copilot summaries are not stored anywhere by GitHub; refresh them by clicking the
  button again after additional commits.

## Verification

```bash
# Confirm Copilot seat is assigned and features enabled for the repo
gh api /repos/{owner}/{repo}/copilot/access \
  | jq '{copilot_ide_code_completions, copilot_chat}'

# List recent PR description update events to verify automation ran
gh pr view {PR_NUMBER} --json body,updatedAt | jq '{updatedAt, bodyLength: .body | length}'
```

## Related

- `github-copilot-code-review-effort-levels.md`
- `github-copilot-coding-agent.md`
- `github-copilot-workspace.md`
- `issue-and-pr-templates.md`
- `github-actions-pr-comment-bot.md`

## Sources

- https://docs.github.com/en/copilot/using-github-copilot/using-copilot-text-completion/creating-a-pull-request-summary-with-github-copilot
- https://docs.github.com/en/copilot/about-github-copilot/github-copilot-features
- https://github.blog/2023-11-08-github-copilot-in-github-com-pull-request-summaries/
