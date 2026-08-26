# deployment-notification-slack

**Issue:** Sending structured, actionable deployment notifications to Slack
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Generic CI/CD notifications ("Build passed") provide no context. Structured notifications with environment, version, deploy link, and rollback instructions reduce MTTR during incidents.

## Pattern / Solution
GitHub Actions with Slack Block Kit:
```yaml
- name: Notify Slack — deploy start
  uses: slackapi/slack-github-action@v1
  with:
    channel-id: C0123DEPLOYS
    payload: |
      {
        "text": "🚀 Deploying `myapp` to *production*",
        "blocks": [
          {
            "type": "header",
            "text": { "type": "plain_text", "text": "Deploying myapp → production" }
          },
          {
            "type": "section",
            "fields": [
              { "type": "mrkdwn", "text": "*Version:*\n`${{ github.sha }}`" },
              { "type": "mrkdwn", "text": "*Branch:*\n`${{ github.ref_name }}`" },
              { "type": "mrkdwn", "text": "*Actor:*\n${{ github.actor }}" },
              { "type": "mrkdwn", "text": "*Run:*\n<${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}|View>" }
            ]
          }
        ]
      }
  env:
    SLACK_BOT_TOKEN: ${{ secrets.SLACK_BOT_TOKEN }}
```

Post-deploy notification with rollback button:
```bash
curl -X POST https://slack.com/api/chat.postMessage \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"channel\": \"C0123DEPLOYS\",
    \"text\": \"Deploy complete\",
    \"blocks\": [{
      \"type\": \"section\",
      \"text\": { \"type\": \"mrkdwn\", \"text\": \"✅ *myapp* deployed to *production*\nVersion: \`${IMAGE_TAG}\`\" },
      \"accessory\": {
        \"type\": \"button\",
        \"text\": { \"type\": \"plain_text\", \"text\": \"Rollback\" },
        \"style\": \"danger\",
        \"url\": \"${ROLLBACK_TRIGGER_URL}\"
      }
    }]
  }"
```

Minimal bash helper (no external action):
```bash
slack_notify() {
  local color=$1 text=$2
  curl -s -X POST "$SLACK_WEBHOOK_URL" \
    -H 'Content-Type: application/json' \
    -d "{\"attachments\":[{\"color\":\"$color\",\"text\":\"$text\",\"ts\":$(date +%s)}]}"
}

slack_notify "good"  "✅ myapp v$TAG deployed to staging"
slack_notify "danger" "❌ myapp deployment FAILED — check CI"
```

## Gotchas
- Incoming webhooks are simpler but cannot update messages; use the Web API with `chat.update` for in-place status updates
- Block Kit buttons require a Slack app with interactive components enabled and a request URL configured
- Slack rate limit is 1 message per second per channel; batch deployment status into one message instead of many
- Do not include raw secrets or env var dumps in Slack messages — Slack logs are accessible to all workspace members

## Related
- `deployment-approval-workflow.md`
- `jenkins-pipeline-patterns.md`
- `post-deploy-monitoring-checklist.md`
