# GitHub Discussions API Workers Community Automation

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Cloudflare Workers OSS project receives dozens of new GitHub Discussions each week. Maintainers manually label questions vs announcements vs show-and-tell posts, post welcome messages for first-time contributors, and close stale discussions that have been idle for 90 days. This takes an hour of maintainer time each week and gets skipped during busy periods. A Cloudflare Worker triggered by GitHub webhook events and a scheduled Cron Trigger can automate all three tasks using the GitHub GraphQL API.

## Context

GitHub Discussions has a dedicated GraphQL API — there is no REST equivalent for most discussion operations. The API supports querying discussions by category, labeling them, creating comments, and locking/closing them. A Cloudflare Worker is a natural host for this automation: it receives the `discussion.created` webhook for welcome messages and labeling, and it runs on a Cron Trigger (once per day) to sweep for stale discussions. The Worker authenticates as a GitHub App installation, which avoids personal access token rotation and provides per-repo installation scoping.

## GitHub GraphQL API: key mutations

```typescript
// src/discussions-api.ts

const GH_GRAPHQL = "https://api.github.com/graphql";

async function graphql<T>(
  query: string,
  variables: Record<string, unknown>,
  token: string
): Promise<T> {
  const res = await fetch(GH_GRAPHQL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      "User-Agent": "cf-discussions-bot/1.0",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify({ query, variables }),
  });
  const json = await res.json<{ data?: T; errors?: Array<{ message: string }> }>();
  if (json.errors?.length) throw new Error(json.errors[0].message);
  return json.data!;
}

// Add a label to a discussion (labelableId is the discussion's node ID)
export async function addLabelToDiscussion(
  labelableId: string,
  labelIds: string[],
  token: string
): Promise<void> {
  await graphql(
    `mutation AddLabel($labelableId: ID!, $labelIds: [ID!]!) {
       addLabelsToLabelable(input: { labelableId: $labelableId, labelIds: $labelIds }) {
         labelable { ... on Discussion { id } }
       }
     }`,
    { labelableId, labelIds },
    token
  );
}

// Post a comment on a discussion
export async function addDiscussionComment(
  discussionId: string,
  body: string,
  token: string
): Promise<string> {
  const data = await graphql<{
    addDiscussionComment: { comment: { id: string } };
  }>(
    `mutation AddComment($discussionId: ID!, $body: String!) {
       addDiscussionComment(input: { discussionId: $discussionId, body: $body }) {
         comment { id }
       }
     }`,
    { discussionId, body },
    token
  );
  return data.addDiscussionComment.comment.id;
}

// Close a discussion (mark as answered or archive)
export async function closeDiscussion(
  discussionId: string,
  reason: "RESOLVED" | "OUTDATED" | "DUPLICATE",
  token: string
): Promise<void> {
  await graphql(
    `mutation CloseDiscussion($discussionId: ID!, $reason: DiscussionCloseReason!) {
       closeDiscussion(input: { discussionId: $discussionId, stateReason: $reason }) {
         discussion { id closed }
       }
     }`,
    { discussionId, reason },
    token
  );
}

// Query stale open discussions (last activity older than cutoffDays)
export async function fetchStaleDiscussions(
  owner: string,
  repo: string,
  cutoffDays: number,
  token: string
): Promise<Array<{ id: string; title: string; updatedAt: string }>> {
  const cutoff = new Date(Date.now() - cutoffDays * 86_400_000).toISOString();

  const data = await graphql<{
    repository: {
      discussions: {
        nodes: Array<{ id: string; title: string; updatedAt: string; closed: boolean }>;
      };
    };
  }>(
    `query StaleDiscussions($owner: String!, $repo: String!, $first: Int!) {
       repository(owner: $owner, name: $repo) {
         discussions(first: $first, states: [OPEN], orderBy: { field: UPDATED_AT, direction: ASC }) {
           nodes { id title updatedAt closed }
         }
       }
     }`,
    { owner, repo, first: 50 },
    token
  );

  return data.repository.discussions.nodes.filter(
    (d) => !d.closed && d.updatedAt < cutoff
  );
}
```

## Webhook handler: welcome message and auto-label

```typescript
// src/index.ts
import { verifyWebhookSignature } from "./verify";
import {
  addLabelToDiscussion,
  addDiscussionComment,
  fetchStaleDiscussions,
  closeDiscussion,
} from "./discussions-api";
import { getInstallationToken } from "./github-app-auth";

export interface Env {
  GITHUB_APP_ID: string;
  GITHUB_PRIVATE_KEY: string;     // PEM, stored as a secret
  GITHUB_WEBHOOK_SECRET: string;
  QUESTION_LABEL_ID: string;      // GraphQL node ID for the "question" label
  SHOW_TELL_LABEL_ID: string;     // GraphQL node ID for the "show-and-tell" label
  REPO_INSTALLATION_ID: string;   // GitHub App installation ID for the target repo
}

interface DiscussionPayload {
  action: "created" | "edited" | "deleted";
  discussion: {
    node_id: string;
    title: string;
    body: string;
    category: { name: string; slug: string };
    user: { login: string };
    repository_url: string;
  };
  repository: { owner: { login: string }; name: string };
  sender: { login: string };
  installation?: { id: number };
}

async function handleDiscussionCreated(
  payload: DiscussionPayload,
  env: Env
): Promise<void> {
  const token = await getInstallationToken(
    env.GITHUB_APP_ID,
    env.GITHUB_PRIVATE_KEY,
    Number(env.REPO_INSTALLATION_ID)
  );

  const discussion = payload.discussion;
  const slug = discussion.category.slug;

  // Auto-label based on category
  const labelMap: Record<string, string> = {
    "q-a": env.QUESTION_LABEL_ID,
    "show-and-tell": env.SHOW_TELL_LABEL_ID,
  };
  if (slug in labelMap) {
    await addLabelToDiscussion(discussion.node_id, [labelMap[slug]], token);
  }

  // Welcome message for the discussion author
  const welcome = `
Thanks for posting, @${discussion.user.login}! 👋

${slug === "q-a" ? "If a reply answers your question, please mark it as the answer to help others find the solution." : "We love seeing what the community builds — feel free to share screenshots or links!"}

Our [contributing guide](https://github.com/${payload.repository.owner.login}/${payload.repository.name}/blob/main/CONTRIBUTING.md) has tips for getting the most out of community discussions.
`.trim();

  await addDiscussionComment(discussion.node_id, welcome, token);
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const body = await request.text();
    await verifyWebhookSignature(request, body, env.GITHUB_WEBHOOK_SECRET);

    const event = request.headers.get("X-GitHub-Event");
    if (event !== "discussion") return new Response("Ignored", { status: 200 });

    const payload: DiscussionPayload = JSON.parse(body);
    if (payload.action === "created") {
      ctx.waitUntil(handleDiscussionCreated(payload, env));
    }

    return new Response("Accepted", { status: 202 });
  },

  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    // Daily stale discussion sweep
    ctx.waitUntil(sweepStaleDiscussions(env));
  },
};

async function sweepStaleDiscussions(env: Env): Promise<void> {
  const token = await getInstallationToken(
    env.GITHUB_APP_ID,
    env.GITHUB_PRIVATE_KEY,
    Number(env.REPO_INSTALLATION_ID)
  );

  const owner = "your-org";
  const repo = "your-repo";
  const stale = await fetchStaleDiscussions(owner, repo, 90, token);

  console.log(`Found ${stale.length} stale discussions (>90 days idle)`);

  for (const d of stale) {
    await addDiscussionComment(
      d.id,
      "This discussion has been idle for 90 days. Closing as outdated — please open a new one if this is still relevant.",
      token
    );
    await closeDiscussion(d.id, "OUTDATED", token);
    // Rate limit guard: 1 req/sec is well within GitHub's 5000/hour limit
    await new Promise((r) => setTimeout(r, 1000));
  }
}
```

## wrangler.toml Cron Trigger configuration

```toml
# wrangler.toml
name = "discussions-bot"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[triggers]
crons = ["0 6 * * *"]   # 06:00 UTC daily stale sweep

[vars]
GITHUB_APP_ID = "123456"
REPO_INSTALLATION_ID = "78901234"
QUESTION_LABEL_ID = "LA_kwDOABCDEF8AAAAAAAAABCD"
SHOW_TELL_LABEL_ID = "LA_kwDOABCDEF8AAAAAAAAABCE"
```

Secrets (never in `wrangler.toml`):

```bash
wrangler secret put GITHUB_PRIVATE_KEY
wrangler secret put GITHUB_WEBHOOK_SECRET
```

## Finding GraphQL label node IDs

```bash
gh api graphql -f query='
  query {
    repository(owner: "your-org", name: "your-repo") {
      labels(first: 50) {
        nodes { id name }
      }
    }
  }
' | jq '.data.repository.labels.nodes[] | select(.name == "question")'
# Output: { "id": "LA_kwDO...", "name": "question" }
```

## Anti-patterns

- Using the REST API for discussion operations — most write operations (labeling, commenting on discussions) are GraphQL-only. The REST discussions endpoint is read-only.
- Closing stale discussions without posting a comment first — contributors receive no notification and cannot re-open the discussion to provide an update.
- Processing webhook events synchronously inside `fetch()` without `ctx.waitUntil()` — if the GraphQL mutation takes longer than the response timeout, the Worker is terminated mid-operation.
- Posting welcome comments for every discussion author regardless of prior activity — first-timers benefit from the message, but prolific contributors see it as spam. Check `sender.type` or maintain a KV set of greeted users.

## Gotchas

- GitHub Discussions GraphQL mutations require the GitHub App to have the `Discussions: write` permission on the installation. Adding `read` is insufficient for labeling and commenting.
- The `closeDiscussion` mutation accepts `RESOLVED`, `OUTDATED`, and `DUPLICATE` as reasons. `RESOLVED` should only be used when a discussion has an accepted answer; use `OUTDATED` for time-based sweeps.
- Discussion category slugs (`q-a`, `show-and-tell`) are repo-specific. Slugs cannot be assumed — query them via `repository.discussionCategories` in GraphQL before hardcoding.
- GitHub limits GraphQL mutations to 5000 points per hour per installation token. Each mutation costs ~1 point. A sweep that closes 100 stale discussions in one run is safe, but batch operations on large repos may need paging and rate limit headers.
- The `discussion.created` webhook is fired even for announcements posted by the repository owner. Filter on `payload.discussion.category.slug` or `payload.sender.type` to avoid welcoming the bot owner.

## Verification

```bash
# Trigger the stale sweep manually via the Cloudflare dashboard
# or test with a cron preview
wrangler triggers crons --env production

# Test the webhook handler locally with wrangler dev
wrangler dev --env staging
# Then in another terminal, send a mock webhook:
curl -X POST http://localhost:8787/ \
  -H "X-GitHub-Event: discussion" \
  -H "X-Hub-Signature-256: sha256=<computed>" \
  -H "Content-Type: application/json" \
  -d @test/fixtures/discussion-created.json
# Expected: 202 Accepted, welcome comment appears on the test discussion
```

## Related

- `github-app-webhook-workers-handler.md`
- `github-apps-installation-tokens.md`
- `github-graphql-api-patterns.md`
- `github-webhook-signing-verification.md`
- `github-actions-scheduled-cron-workers-maintenance.md`

## Sources

- https://docs.github.com/en/graphql/reference/mutations#adddiscussioncomment
- https://docs.github.com/en/graphql/reference/mutations#closediscussion
- https://docs.github.com/en/webhooks/webhook-events-and-payloads#discussion
- https://developers.cloudflare.com/workers/runtime-apis/scheduled-controller/
- https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app
