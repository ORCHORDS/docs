# Deployment Notification Webhooks to Slack and Teams via Workers

- Date: 2026-08-22
- Author: example.com
- Status: production

## The Problem: Deployment Events That No One Sees

CI pipelines send deploy events to a void. Teams miss rollbacks, new versions, or failures because notification logic is bolted onto CI YAML as fragile shell one-liners — no diff summaries, no rollback buttons, no routing by team. The result is alert fatigue from noisy pings and under-alerting when something actually goes wrong.

This article describes a Cloudflare Worker that acts as a centralized deployment notification hub. CI pipelines POST structured deploy events to the Worker; the Worker formats rich messages for Slack and Microsoft Teams, includes a commit diff summary, and embeds actionable deep-links for one-click rollbacks. A D1 table stores per-team notification preferences so each team controls which events wake them up and in which channel.

The Worker handles both platforms from a single endpoint, eliminating per-repo webhook management and giving the platform team one place to evolve the message schema.

## Context

- Cloudflare Workers for the notification hub
- D1 for team notification preference storage
- Slack Block Kit and Teams Adaptive Cards for rich formatting
- GitHub API for fetching commit diff summaries
- CI pipelines (GitHub Actions, GitLab CI) calling the Worker via authenticated POST

## D1 Schema: Team Notification Preferences

```sql
-- schema.sql
CREATE TABLE IF NOT EXISTS team_prefs (
  team            TEXT PRIMARY KEY,
  slack_webhook   TEXT,
  teams_webhook   TEXT,
  notify_on       TEXT NOT NULL DEFAULT 'deploy,rollback,failure',
  -- comma-separated: deploy | rollback | failure | canary | success
  min_severity    TEXT NOT NULL DEFAULT 'info',
  -- info | warning | critical
  muted_until     INTEGER        -- Unix ms; NULL = not muted
);

CREATE TABLE IF NOT EXISTS deploy_log (
  id           TEXT PRIMARY KEY,
  team         TEXT NOT NULL,
  service      TEXT NOT NULL,
  event_type   TEXT NOT NULL,
  version_from TEXT,
  version_to   TEXT,
  triggered_by TEXT,
  notified_at  INTEGER
);
```

## Deploy Event Worker: Routing and Formatting

```ts
// src/notify-worker.ts
import { WorkerEntrypoint } from 'cloudflare:workers';

interface Env {
  DB: D1Database;
  NOTIFY_SECRET: string;
  GITHUB_TOKEN: string;
}

interface DeployEvent {
  team: string;
  service: string;
  event_type: 'deploy' | 'rollback' | 'failure' | 'canary' | 'success';
  version_from?: string;
  version_to: string;
  commit_sha?: string;
  repo?: string;           // e.g. "org/repo"
  triggered_by: string;
  deploy_url?: string;     // link to CI run
  rollback_url?: string;   // deep-link to trigger rollback workflow
  environment: string;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.headers.get('X-Notify-Secret') !== env.NOTIFY_SECRET) {
      return new Response('Unauthorized', { status: 401 });
    }

    const event = await req.json<DeployEvent>();
    const pref = await env.DB.prepare(
      `SELECT * FROM team_prefs WHERE team = ?`
    ).bind(event.team).first<{
      slack_webhook: string | null;
      teams_webhook: string | null;
      notify_on: string;
      muted_until: number | null;
    }>();

    if (!pref) {
      return Response.json({ skipped: 'no_prefs' });
    }

    // Check mute window
    if (pref.muted_until && pref.muted_until > Date.now()) {
      return Response.json({ skipped: 'muted' });
    }

    // Check event filter
    if (!pref.notify_on.split(',').includes(event.event_type)) {
      return Response.json({ skipped: 'filtered' });
    }

    const diffSummary = event.commit_sha && event.repo
      ? await fetchDiffSummary(env.GITHUB_TOKEN, event.repo, event.version_from, event.commit_sha)
      : null;

    const results: Record<string, string> = {};

    if (pref.slack_webhook) {
      const body = buildSlackMessage(event, diffSummary);
      const res = await fetch(pref.slack_webhook, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      results.slack = res.ok ? 'sent' : `error:${res.status}`;
    }

    if (pref.teams_webhook) {
      const body = buildTeamsCard(event, diffSummary);
      const res = await fetch(pref.teams_webhook, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      results.teams = res.ok ? 'sent' : `error:${res.status}`;
    }

    await env.DB.prepare(`
      INSERT INTO deploy_log (id, team, service, event_type, version_from, version_to, triggered_by, notified_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `).bind(crypto.randomUUID(), event.team, event.service, event.event_type,
             event.version_from ?? null, event.version_to, event.triggered_by, Date.now()).run();

    return Response.json(results);
  },
} satisfies ExportedHandler<Env>;

async function fetchDiffSummary(token: string, repo: string, from?: string, to?: string): Promise<string | null> {
  if (!from || !to) return null;
  const res = await fetch(
    `https://api.github.com/repos/${repo}/compare/${from}...${to}`,
    { headers: { Authorization: `Bearer ${token}`, 'User-Agent': 'deploy-notifier/1.0' } }
  );
  if (!res.ok) return null;
  const data = await res.json<any>();
  const files: string[] = (data.files ?? []).slice(0, 5).map((f: any) => `• \`${f.filename}\` (+${f.additions}/-${f.deletions})`);
  return files.length ? files.join('\n') : null;
}
```

## Slack Block Kit Message Builder

```ts
function buildSlackMessage(event: DeployEvent, diff: string | null) {
  const color = event.event_type === 'failure' ? '#E01E5A'
              : event.event_type === 'rollback' ? '#ECB22E'
              : '#2EB67D';

  const blocks: any[] = [
    {
      type: 'section',
      text: {
        type: 'mrkdwn',
        text: `*${emoji(event.event_type)} ${event.service}* → \`${event.environment}\`\n`
            + `Version: \`${event.version_from ?? '?'}\` → \`${event.version_to}\`\n`
            + `By: ${event.triggered_by}`,
      },
    },
  ];

  if (diff) {
    blocks.push({
      type: 'section',
      text: { type: 'mrkdwn', text: `*Changed files:*\n${diff}` },
    });
  }

  const actions: any[] = [];
  if (event.deploy_url) {
    actions.push({ type: 'button', text: { type: 'plain_text', text: 'View CI Run' }, url: event.deploy_url });
  }
  if (event.rollback_url && event.event_type !== 'rollback') {
    actions.push({
      type: 'button',
      text: { type: 'plain_text', text: 'Rollback' },
      style: 'danger',
      url: event.rollback_url,
      confirm: { title: { type: 'plain_text', text: 'Rollback?' }, text: { type: 'mrkdwn', text: 'This triggers an immediate rollback.' }, confirm: { type: 'plain_text', text: 'Yes, rollback' }, deny: { type: 'plain_text', text: 'Cancel' } },
    });
  }
  if (actions.length) {
    blocks.push({ type: 'actions', elements: actions });
  }

  return { attachments: [{ color, blocks }] };
}

function buildTeamsCard(event: DeployEvent, diff: string | null) {
  const facts = [
    { title: 'Service', value: event.service },
    { title: 'Environment', value: event.environment },
    { title: 'Version', value: `${event.version_from ?? '?'} → ${event.version_to}` },
    { title: 'Triggered by', value: event.triggered_by },
  ];
  if (diff) facts.push({ title: 'Changed files', value: diff.replace(/•/g, '-') });

  const actions: any[] = [];
  if (event.deploy_url) {
    actions.push({ '@type': 'OpenUri', name: 'View CI Run', targets: [{ os: 'default', uri: event.deploy_url }] });
  }
  if (event.rollback_url && event.event_type !== 'rollback') {
    actions.push({ '@type': 'OpenUri', name: 'Rollback', targets: [{ os: 'default', uri: event.rollback_url }] });
  }

  return {
    '@type': 'MessageCard',
    '@context': 'http://schema.org/extensions',
    themeColor: event.event_type === 'failure' ? 'E01E5A' : '2EB67D',
    summary: `${event.service} ${event.event_type} in ${event.environment}`,
    sections: [{ facts }],
    potentialAction: actions,
  };
}

function emoji(type: string) {
  return { deploy: '🚀', rollback: '⏪', failure: '🔴', canary: '🐤', success: '✅' }[type] ?? '📦';
}
```

## Anti-patterns

- Hardcoding Slack webhook URLs in GitHub Actions secrets per repo — centralizing in D1 means one update propagates everywhere
- Sending notifications from inside `wrangler deploy` shell steps — network errors block the deploy; the notification Worker should be fire-and-forget from CI
- Not rate-limiting the notification endpoint — a CI bug can spam channels; add a simple Durable Object or KV-based rate limiter per team
- Including full diffs in the message — Slack blocks have a 3001-character limit per section; summarize to top-5 files

## Gotchas

- Slack's Block Kit `confirm` dialog on buttons only works in interactive components; Incoming Webhooks cannot respond to button clicks — use workflow triggers or Slash commands for true interactive rollbacks
- Teams Adaptive Cards replace MessageCard in newer connectors; check which card type your Teams version supports
- GitHub's compare API can return 404 if commits are force-pushed or the repo is private and the token lacks `repo` scope
- D1 `muted_until` field must be checked in UTC milliseconds — time zone bugs silently suppress or send notifications

## Verification

```ts
// Confirm the last deploy log entry for a known team
const row = await env.DB.prepare(
  `SELECT * FROM deploy_log WHERE team = ? ORDER BY notified_at DESC LIMIT 1`
).bind('platform').first<{ event_type: string; service: string }>();
console.assert(row !== null, 'No notification log found for team:platform');
```

## Related

- [deployment-notification-slack.md](deployment-notification-slack.md)
- [deployment-approval-workflow.md](deployment-approval-workflow.md)
- [on-call-escalation-policy.md](on-call-escalation-policy.md)
- rollbacks.md
- [feature-flag-deploy-coupling.md](feature-flag-deploy-coupling.md)

## Sources

- https://api.slack.com/messaging/webhooks
- https://api.slack.com/reference/block-kit/blocks
- https://learn.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/how-to/connectors-using
- https://docs.github.com/en/rest/commits/commits#compare-two-commits
- https://developers.cloudflare.com/d1/
