# GitHub Actions PR Slash Command Dispatch for Deployment Previews
- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

Reviewers want to trigger on-demand deployment previews, integration tests, or rollback actions
directly from PR comments using natural commands like `/preview`, `/deploy staging`, or
`/rollback`, without switching to the GitHub Actions UI. You want ChatOps-style commands that are
auditable (all commands appear in PR comment history), permission-aware (only team members can
trigger), and wired to your Cloudflare Workers preview deployment pipeline.

## Context

GitHub fires the `issue_comment` event when a comment is posted on an issue or pull request.
A workflow triggered by `issue_comment` runs in the context of the default branch, not the PR
branch — this is a key security distinction. Workflows triggered on PR comments from forked
repos run with read-only permissions by default; the approach in this article is safe for public
repos because permission checks happen before any deployment code runs.

Key concepts:
- **`issue_comment` event**: fires on any comment; the `github.event.issue.pull_request` field
  distinguishes PR comments from issue comments.
- **`actions/github-script`**: executes JavaScript inside the Actions runner with the GitHub API
  client pre-authenticated.
- **`repository_dispatch`**: allows a workflow to trigger another workflow with a custom event
  type and payload; useful for separating the parse-command job from the deploy job.
- **`pull_request_target`**: alternative trigger; runs in the default branch context with write
  permissions even from forks. Requires careful security gating.

## Architecture

```
PR comment: "/preview mobile-api"
         │
         ▼
[issue_comment workflow]
  1. Parse command
  2. Check actor team membership
  3. React with 👀 to acknowledge
  4. Dispatch repository_dispatch → event: "deploy-preview"
         │
         ▼
[deploy-preview workflow]  (triggered by repository_dispatch)
  1. Checkout PR branch using ref from payload
  2. Deploy Cloudflare Worker preview
  3. Post result comment to PR
```

## Step 1: Command parser workflow

```yaml
# .github/workflows/slash-command-dispatch.yml
name: Slash Command Dispatch

on:
  issue_comment:
    types: [created]

jobs:
  parse-command:
    # Only run on PR comments containing a slash command
    if: |
      github.event.issue.pull_request != null &&
      startsWith(github.event.comment.body, '/')
    runs-on: ubuntu-latest
    permissions:
      contents: read
      issues: write        # to add reactions and comments
      pull-requests: write

    steps:
      - name: Check actor team membership
        id: check-team
        uses: actions/github-script@v7
        with:
          script: |
            const actor = context.actor;
            const org = context.repo.owner;
            const team = 'deploy-team';     // GitHub team slug that can trigger deploys

            try {
              await github.rest.teams.getMembershipForUserInOrg({
                org,
                team_slug: team,
                username: actor,
              });
              core.setOutput('authorized', 'true');
            } catch (e) {
              if (e.status === 404) {
                core.setOutput('authorized', 'false');
                core.notice(`@${actor} is not a member of ${org}/${team}; command ignored.`);
              } else {
                throw e;
              }
            }

      - name: Parse slash command
        id: parse
        if: steps.check-team.outputs.authorized == 'true'
        uses: actions/github-script@v7
        with:
          script: |
            const body = context.payload.comment.body.trim();
            const [command, ...args] = body.split(/\s+/);
            const supported = ['/preview', '/deploy', '/rollback', '/test-e2e'];
            if (!supported.includes(command)) {
              core.setOutput('valid', 'false');
              return;
            }
            core.setOutput('valid', 'true');
            core.setOutput('command', command.slice(1));   // strip leading /
            core.setOutput('args', args.join(' '));

      - name: React to command (acknowledge)
        if: |
          steps.check-team.outputs.authorized == 'true' &&
          steps.parse.outputs.valid == 'true'
        uses: actions/github-script@v7
        with:
          script: |
            await github.rest.reactions.createForIssueComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              comment_id: context.payload.comment.id,
              content: 'eyes',
            });

      - name: Get PR ref
        id: pr-ref
        if: |
          steps.check-team.outputs.authorized == 'true' &&
          steps.parse.outputs.valid == 'true'
        uses: actions/github-script@v7
        with:
          script: |
            const pr = await github.rest.pulls.get({
              owner: context.repo.owner,
              repo: context.repo.repo,
              pull_number: context.payload.issue.number,
            });
            core.setOutput('head_sha', pr.data.head.sha);
            core.setOutput('head_ref', pr.data.head.ref);
            core.setOutput('pr_number', String(context.payload.issue.number));

      - name: Dispatch command event
        if: |
          steps.check-team.outputs.authorized == 'true' &&
          steps.parse.outputs.valid == 'true'
        uses: actions/github-script@v7
        with:
          script: |
            await github.rest.repos.createDispatchEvent({
              owner: context.repo.owner,
              repo: context.repo.repo,
              event_type: 'slash-command-${{ steps.parse.outputs.command }}',
              client_payload: {
                command: '${{ steps.parse.outputs.command }}',
                args: '${{ steps.parse.outputs.args }}',
                pr_number: '${{ steps.pr-ref.outputs.pr_number }}',
                head_sha: '${{ steps.pr-ref.outputs.head_sha }}',
                head_ref: '${{ steps.pr-ref.outputs.head_ref }}',
                actor: context.actor,
                comment_id: String(context.payload.comment.id),
              },
            });
```

## Step 2: Preview deploy workflow

```yaml
# .github/workflows/deploy-preview-command.yml
name: Deploy Preview (Slash Command)

on:
  repository_dispatch:
    types: [slash-command-preview, slash-command-deploy]

jobs:
  deploy-preview:
    runs-on: ubuntu-latest
    environment: preview
    permissions:
      contents: read
      pull-requests: write
      id-token: write    # for Cloudflare OIDC

    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.client_payload.head_sha }}
          fetch-depth: 1

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Deploy preview Worker
        id: deploy
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CF_API_TOKEN }}
          command: deploy --env preview --var PREVIEW_SUFFIX:pr-${{ github.event.client_payload.pr_number }}

      - name: Extract preview URL
        id: url
        run: |
          # Wrangler outputs the Worker URL; parse from deploy output
          URL=$(echo "${{ steps.deploy.outputs.command-output }}" | \
            grep -oP 'https://[a-z0-9\-]+\.workers\.dev')
          echo "preview_url=$URL" >> "$GITHUB_OUTPUT"

      - name: Post success comment
        uses: actions/github-script@v7
        with:
          script: |
            const actor = '${{ github.event.client_payload.actor }}';
            const previewUrl = '${{ steps.url.outputs.preview_url }}';
            const sha = '${{ github.event.client_payload.head_sha }}'.slice(0, 7);
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: Number('${{ github.event.client_payload.pr_number }}'),
              body: [
                `✅ **Preview deployed** by @${actor}`,
                ``,
                `- **URL**: ${previewUrl}`,
                `- **Commit**: \`${sha}\``,
                `- **Workflow**: View run`,
              ].join('\n'),
            });

      - name: Post failure comment
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: Number('${{ github.event.client_payload.pr_number }}'),
              body: [
                `❌ **Preview deploy failed**`,
                ``,
                `View run`,
              ].join('\n'),
            });
```

## Step 3: E2E test trigger command

```yaml
# .github/workflows/e2e-command.yml
name: E2E Tests (Slash Command)

on:
  repository_dispatch:
    types: [slash-command-test-e2e]

jobs:
  e2e:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write

    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.client_payload.head_sha }}

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Run Playwright E2E
        run: npx playwright test
        env:
          BASE_URL: ${{ github.event.client_payload.args }}   # e.g. preview URL passed as arg

      - name: Post E2E results
        if: always()
        uses: actions/github-script@v7
        with:
          script: |
            const conclusion = '${{ job.status }}' === 'success' ? '✅ passed' : '❌ failed';
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: Number('${{ github.event.client_payload.pr_number }}'),
              body: `E2E tests ${conclusion} — View run`,
            });
```

## Supported commands summary

| Command | Example | Effect |
|---|---|---|
| `/preview` | `/preview` | Deploys a Cloudflare Worker preview for the PR |
| `/deploy staging` | `/deploy staging` | Deploys to the staging environment |
| `/test-e2e https://...` | `/test-e2e https://pr-42.workers.dev` | Runs Playwright against a URL |
| `/rollback` | `/rollback` | Rolls back the staging Worker to the previous deployment |

## Permission model

Only members of the `deploy-team` GitHub team (configurable) can trigger commands. The team
membership check runs first, before any resource-consuming steps. Unauthorized attempts are
silently ignored (no reaction, no comment) to avoid leaking information about team membership
to public actors.

For organization repos, the team must be in the same organization as the repository.

## Anti-patterns

- **Using `pull_request_target` without careful security gating**: this trigger runs with write
  permissions and access to secrets even for fork PRs. Checking team membership is mandatory.
- **Dispatching without extracting the PR ref**: `repository_dispatch` runs on the default
  branch by default. Always pass `head_sha` in the payload and check out explicitly.
- **Broadcasting to all repo members**: scope slash commands to a specific team, not `CODEOWNERS`
  or all collaborators, to limit blast radius.
- **Not reacting to the comment**: without the 👀 reaction, users cannot tell if the command
  was received. Acknowledge before dispatching.
- **Hardcoding the deploy team slug**: make it an organization variable or repository variable
  so it can change without editing the workflow.

## Gotchas

- `issue_comment` fires for both issues and PRs. The `if` condition
  `github.event.issue.pull_request != null` is required to scope to PRs only.
- `repository_dispatch` payloads have a maximum size of 65,535 bytes.
- The `actor` in `issue_comment` is the commenter; in `repository_dispatch` it becomes the
  GitHub Actions app. Pass the original actor in `client_payload` for attribution.
- `teams.getMembershipForUserInOrg` returns 404 for non-members and 302 for members outside the
  org visibility. Handle both cases explicitly.

## Verification

1. Post `/preview` as a team member and confirm the 👀 reaction appears within seconds.
2. Confirm the `slash-command-dispatch` workflow run appears in the Actions tab.
3. Confirm the `deploy-preview-command` workflow starts via `repository_dispatch`.
4. Confirm a success comment appears on the PR with the preview URL.
5. Post `/preview` as a non-team member and confirm no reaction and no workflow run appears.

## Related

- `github-actions-cloudflare-deploy-workflow.md`
- `github-actions-pr-comment-bot.md`
- `github-actions-environments.md`
- `github-actions-workflow-dispatch.md`

## Sources

- https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#issue_comment
- https://docs.github.com/en/rest/repos/repos#create-a-repository-dispatch-event
- https://github.com/peter-evans/slash-command-dispatch
