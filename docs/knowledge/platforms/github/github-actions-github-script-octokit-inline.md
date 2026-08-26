# Inline Octokit API Calls with actions/github-script

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You need to call the GitHub API from a workflow step — add a label, post a comment, create a
deployment status, or query repository metadata — but the logic is too small to justify
authoring and maintaining a full JavaScript action. `actions/github-script` lets you write
inline JavaScript in a `with.script` block with a pre-authenticated Octokit client and the
full `@actions/core` toolkit available as globals.

## Context

`actions/github-script` (maintained by GitHub) runs arbitrary JavaScript in a Node.js
environment. It pre-wires:

- `github` — an authenticated Octokit REST + GraphQL client scoped to `GITHUB_TOKEN` (or a
  PAT/app token you supply via `github-token`)
- `context` — same as `github.context` in a custom action
- `core` — `@actions/core`
- `exec` — `@actions/exec`
- `glob` — `@actions/glob`
- `io` — `@actions/io`
- `fetch` — native Node 20 fetch

The script runs synchronously unless you `return` a promise (async functions work
transparently). The return value becomes the step output `result`.

---

## Basic Usage: Post a PR Comment

```yaml
- name: Comment on PR
  uses: actions/github-script@v7
  with:
    script: |
      await github.rest.issues.createComment({
        owner: context.repo.owner,
        repo:  context.repo.repo,
        issue_number: context.issue.number,
        body: `Deploy preview ready: https://preview-${context.sha.slice(0,7)}.example.com`,
      });
```

`context.issue.number` is available on `pull_request`, `issue_comment`, and similar events.
On other events it is `undefined` — guard with `if (context.issue.number)`.

---

## Capturing Return Values as Step Outputs

```yaml
- id: get-release
  uses: actions/github-script@v7
  with:
    script: |
      const { data } = await github.rest.repos.getLatestRelease({
        owner: context.repo.owner,
        repo:  context.repo.repo,
      });
      return data.tag_name;
    result-encoding: string   # default is json; use string for plain text

- name: Use tag
  run: echo "Latest release is ${{ steps.get-release.outputs.result }}"
```

`result-encoding: json` (default) serialises the return value with `JSON.stringify`. Use
`string` when the return value is already a plain string.

---

## Labels, Milestones, and Assignments

```yaml
- name: Triage new issue
  if: github.event_name == 'issues' && github.event.action == 'opened'
  uses: actions/github-script@v7
  with:
    script: |
      const labels = ['needs-triage'];
      const title  = context.payload.issue.title.toLowerCase();

      if (title.includes('workers') || title.includes('cloudflare')) {
        labels.push('platform: cloudflare');
      }
      if (title.includes('d1') || title.includes('database')) {
        labels.push('component: d1');
      }

      await github.rest.issues.addLabels({
        owner:        context.repo.owner,
        repo:         context.repo.repo,
        issue_number: context.issue.number,
        labels,
      });

      core.info(`Applied labels: ${labels.join(', ')}`);
```

---

## Creating and Updating Deployment Statuses

```yaml
- name: Create deployment
  id: create-deploy
  uses: actions/github-script@v7
  with:
    script: |
      const { data } = await github.rest.repos.createDeployment({
        owner:       context.repo.owner,
        repo:        context.repo.repo,
        ref:         context.sha,
        environment: 'production',
        auto_merge:  false,
        required_contexts: [],
        description: 'Cloudflare Workers deploy',
      });
      return data.id;

- name: Deploy to Workers
  id: wrangler-deploy
  run: npx wrangler deploy --env production
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

- name: Update deployment status
  if: always()
  uses: actions/github-script@v7
  with:
    script: |
      const deployId = ${{ steps.create-deploy.outputs.result }};
      const success  = '${{ steps.wrangler-deploy.outcome }}' === 'success';

      await github.rest.repos.createDeploymentStatus({
        owner:         context.repo.owner,
        repo:          context.repo.repo,
        deployment_id: deployId,
        state:         success ? 'success' : 'failure',
        environment_url: success
          ? 'https://myapp.example.workers.dev'
          : undefined,
        description: success ? 'Deploy succeeded' : 'Deploy failed',
      });
```

---

## GraphQL Queries

```yaml
- name: Fetch PR review decision
  id: review-state
  uses: actions/github-script@v7
  with:
    script: |
      const { repository } = await github.graphql(`
        query ($owner: String!, $repo: String!, $number: Int!) {
          repository(owner: $owner, name: $repo) {
            pullRequest(number: $number) {
              reviewDecision
              mergeable
            }
          }
        }
      `, {
        owner:  context.repo.owner,
        repo:   context.repo.repo,
        number: context.issue.number,
      });

      const pr = repository.pullRequest;
      core.setOutput('review-decision', pr.reviewDecision ?? 'UNKNOWN');
      core.setOutput('mergeable',       pr.mergeable);

      if (pr.reviewDecision !== 'APPROVED') {
        core.setFailed(`PR not approved: ${pr.reviewDecision}`);
      }
```

---

## Using a Custom Token (GitHub App Installation Token)

```yaml
- name: Generate app token
  id: app-token
  uses: actions/create-github-app-token@v1
  with:
    app-id:          ${{ vars.BOT_APP_ID }}
    private-key:     ${{ secrets.BOT_PRIVATE_KEY }}
    owner:           ${{ github.repository_owner }}

- name: Comment as bot
  uses: actions/github-script@v7
  with:
    github-token: ${{ steps.app-token.outputs.token }}
    script: |
      await github.rest.issues.createComment({
        owner:        context.repo.owner,
        repo:         context.repo.repo,
        issue_number: context.issue.number,
        body:         '✅ Automated checks passed.',
      });
```

Providing `github-token` replaces the default `GITHUB_TOKEN`; the Octokit client is
re-initialised with the supplied value.

---

## Anti-patterns

- **Passing user-controlled data directly into `script:`** — the `script` field is evaluated
  as JavaScript. Never interpolate `${{ github.event.pull_request.title }}` or other
  user-supplied content into the script string; use `process.env` instead:
  ```yaml
  env:
    PR_TITLE: ${{ github.event.pull_request.title }}
  script: |
    const title = process.env.PR_TITLE;
  ```
- **Ignoring pagination** — `github.rest.issues.listComments` returns at most 30 items by
  default. Use `github.paginate` for full result sets.
- **Using `result-encoding: string` on an object return value** — this produces `[object Object]`.
  Omit the field (default `json`) when returning structured data.
- **Storing the whole Octokit response** — `const data = await github.rest…` returns the
  Axios-style `{ data, headers, status }` wrapper; destructure to `.data` first.

---

## Gotchas

- `context.issue.number` throws on workflow events that have no issue/PR number; check the
  triggering event with `context.eventName` before accessing it.
- `github-script@v7` targets Node 20; avoid `require()` for ESM-only packages — use dynamic
  `await import()` instead.
- The `GITHUB_TOKEN` passed implicitly has only the permissions granted to the workflow job.
  Add `permissions: issues: write` (or the relevant scope) at the job level.
- Scripts longer than ~50 lines become hard to maintain inline; move logic to a versioned
  JavaScript action instead.
- `return` at the top level is required to produce output; a script that only calls
  `core.setOutput` still works but `steps.id.outputs.result` will be empty.

---

## Verification

```yaml
- name: Debug context
  uses: actions/github-script@v7
  with:
    script: |
      core.info(JSON.stringify({
        event:  context.eventName,
        ref:    context.ref,
        sha:    context.sha,
        actor:  context.actor,
        issue:  context.issue,
      }, null, 2));
```

Check the Actions step log; Octokit calls also print the HTTP method + URL at `debug` level
when `ACTIONS_STEP_DEBUG=true` is set as a repository secret.

---

## Related

- `github-actions-javascript-typescript-action-authoring.md` — full action when logic exceeds inline comfort
- `github-actions-pr-comment-bot.md` — PR comment workflows
- `github-deployment-api-workers-status-tracking.md` — deployment status integration
- `github-graphql-api-patterns.md` — GraphQL query patterns

---

## Sources

- https://github.com/actions/github-script
- https://octokit.github.io/rest.js
- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/evaluate-expressions-in-workflows-and-actions
- https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions#using-scripts-in-github-actions
