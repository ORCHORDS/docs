# GitHub Actions: AI-Powered PR Review Using Workers AI

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Pull requests receive delayed feedback because human reviewers are overloaded, or small PRs get merged without any substantive review.
This article wires GitHub Actions to Cloudflare Workers AI to generate an automated first-pass code review posted as a PR comment.

## Context
Cloudflare Workers AI exposes LLM inference (Llama 3, Mistral, and other models) via a REST API that GitHub Actions can call directly using `CLOUDFLARE_API_TOKEN`.
The workflow fetches the PR diff, splits it into chunks within the model's context window, and calls the `/ai/run/@cf/meta/llama-3.1-8b-instruct` endpoint for each chunk.
Results are aggregated and posted as a formatted PR comment using the GitHub REST API or `gh` CLI.

---

## Workflow: Fetch Diff and Call Workers AI

```yaml
# .github/workflows/ai-pr-review.yml
name: AI PR Review

on:
  pull_request:
    types: [opened, ready_for_review]

permissions:
  contents: read
  pull-requests: write

jobs:
  ai-review:
    # Skip draft PRs and dependency-only changes
    if: |
      github.event.pull_request.draft == false &&
      !contains(github.event.pull_request.labels.*.name, 'skip-ai-review')
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Get PR diff
        id: diff
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh pr diff ${{ github.event.pull_request.number }} \
            --repo ${{ github.repository }} > /tmp/pr.diff
          LINES=$(wc -l < /tmp/pr.diff)
          echo "lines=$LINES" >> "$GITHUB_OUTPUT"
          echo "Diff size: $LINES lines"

      - name: Skip if diff too large
        if: steps.diff.outputs.lines > 2000
        run: |
          echo "Diff too large for AI review (>2000 lines). Skipping."
          exit 0

      - name: Call Workers AI for review
        id: ai_review
        env:
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          CF_API_TOKEN: ${{ secrets.CF_WORKERS_AI_API_TOKEN }}
        run: |
          DIFF=$(cat /tmp/pr.diff)
          # Truncate to ~8000 chars to stay within context window
          DIFF_TRUNCATED="${DIFF:0:8000}"

          PAYLOAD=$(jq -n \
            --arg diff "$DIFF_TRUNCATED" \
            '{
              messages: [
                {
                  role: "system",
                  content: "You are a senior software engineer reviewing a pull request. Analyze the diff and provide concise, actionable feedback. Focus on: bugs, security issues, performance problems, and style violations. Format your response as markdown with sections: ## Summary, ## Issues Found, ## Suggestions. Be brief — max 400 words."
                },
                {
                  role: "user",
                  content: ("Review this PR diff:\n\n```diff\n" + $diff + "\n```")
                }
              ],
              max_tokens: 600
            }')

          RESPONSE=$(curl -sf \
            "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/ai/run/@cf/meta/llama-3.1-8b-instruct" \
            -H "Authorization: Bearer $CF_API_TOKEN" \
            -H "Content-Type: application/json" \
            -d "$PAYLOAD")

          echo "ai_output<<EOF" >> "$GITHUB_OUTPUT"
          echo "$RESPONSE" | jq -r '.result.response' >> "$GITHUB_OUTPUT"
          echo "EOF" >> "$GITHUB_OUTPUT"

      - name: Post AI review as PR comment
        uses: actions/github-script@v7
        env:
          AI_OUTPUT: ${{ steps.ai_review.outputs.ai_output }}
        with:
          script: |
            const MARKER = '<!-- ai-pr-review -->';
            const body = [
              MARKER,
              '### AI Code Review (Workers AI · Llama 3.1 8B)',
              '',
              process.env.AI_OUTPUT || '_No output generated._',
              '',
              '---',
              `_Generated from commit \`${context.sha.slice(0,7)}\`. This review is AI-generated and may contain errors — use it as a starting point, not a final verdict._`,
            ].join('\n');

            const { data: comments } = await github.rest.issues.listComments({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
            });

            const existing = comments.find(c => c.body?.includes(MARKER));

            if (existing) {
              await github.rest.issues.updateComment({
                owner: context.repo.owner,
                repo: context.repo.repo,
                comment_id: existing.id,
                body,
              });
            } else {
              await github.rest.issues.createComment({
                owner: context.repo.owner,
                repo: context.repo.repo,
                issue_number: context.issue.number,
                body,
              });
            }
```

---

## Workers AI Endpoint Reference

```typescript
// Equivalent TypeScript for calling from a Worker (if review is proxied via a Worker)
interface WorkersAIMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

interface AiTextGenerationInput {
  messages: WorkersAIMessage[];
  max_tokens?: number;
  temperature?: number;
}

// From within a Worker bound to the AI binding:
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const diff = await request.text();

    const result = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
      messages: [
        { role: 'system', content: 'You are a code reviewer...' },
        { role: 'user', content: `Review this diff:\n\`\`\`diff\n${diff}\n\`\`\`` },
      ],
      max_tokens: 600,
    } as AiTextGenerationInput);

    return Response.json(result);
  },
} satisfies ExportedHandler<{ AI: Ai }>;
```

```toml
# wrangler.toml (if proxying through a Worker)
[[ai]]
binding = "AI"
```

---

## Filtering Files to Review

Exclude generated, lock, and binary files from the diff before sending to the model:

```bash
      - name: Filter diff to reviewable files
        run: |
          grep -E "^(diff --git|@@|\+|-)" /tmp/pr.diff \
            | grep -v "package-lock.json\|pnpm-lock.yaml\|yarn.lock\|\.min\.js\|dist/" \
            > /tmp/pr-filtered.diff || true
```

---

## Anti-patterns
- Sending the full raw diff without truncation — most models have a 4K–32K token context window; oversized prompts cause truncation or errors.
- Running on every push (`pull_request: [synchronize]`) — generates excessive API calls and comment spam; use `opened` + `ready_for_review` only.
- Using a high-confidence tone in the comment ("This code has a bug") — AI reviews are probabilistic; hedge with "may" and "consider".
- Storing `CF_WORKERS_AI_API_TOKEN` without scoping it to `AI Gateway` or `Workers AI` only — use a scoped token from the Cloudflare dashboard.
- Posting line-level review comments without verifying the diff position mapping — use issue-level comments instead to avoid GitHub API 422 errors.

## Gotchas
- Workers AI rate limits vary by model; the 8B Llama model allows ~150 requests/minute on the free tier — large repos with high PR velocity need AI Gateway caching or a paid tier.
- The `@cf/meta/llama-3.1-8b-instruct` model may produce markdown that GitHub renders differently than expected — always test rendering in a draft PR.
- `GITHUB_OUTPUT` multiline values require the `<<EOF` heredoc delimiter syntax; using `echo "key=value"` for multiline output corrupts the variable.
- The `pull-requests: write` permission must be set at the job level when using `actions/github-script` with a `GITHUB_TOKEN`.
- AI Gateway can cache identical diff reviews; enable it to reduce costs when the same commit is pushed multiple times.

## Verification
```bash
# Manually trigger the workflow on a specific PR via gh CLI
gh workflow run ai-pr-review.yml \
  --repo owner/repo \
  -f ref=refs/pull/42/head

# Check Workers AI usage in the Cloudflare dashboard:
# Workers AI → Overview → Requests (filter by model)

# Confirm comment was posted:
gh pr view 42 --comments --json comments \
  | jq '.comments[] | select(.body | contains("ai-pr-review")) | .createdAt'
```

## Related
- `github-actions-pr-comment-bot.md`
- `github-copilot-code-review-effort-levels.md`
- `github-actions-cloudflare-deploy-workflow.md`
- `github-copilot-coding-agent.md`

## Sources
- https://developers.cloudflare.com/workers-ai/models/llama-3.1-8b-instruct/
- https://developers.cloudflare.com/workers-ai/get-started/rest-api/
- https://docs.github.com/en/rest/pulls/reviews
- https://developers.cloudflare.com/ai-gateway/get-started/
