# github-actions-notify-slack

**Issue:** Sending Slack notifications from GitHub Actions on build events
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams want Slack alerts when deployments succeed, tests fail, or releases are published without polling GitHub manually.

## Pattern / Solution
Using Slack Incoming Webhooks:
```yaml
      - name: Notify Slack
        if: always()
        uses: slackapi/slack-github-action@v2
        with:
          webhook: ${{ secrets.SLACK_WEBHOOK_URL }}
          webhook-type: incoming-webhook
          payload: |
            {
              "text": "Build ${{ job.status }}: ${{ github.repository }}@${{ github.ref_name }}",
              "attachments": [{
                "color": "${{ job.status == 'success' && 'good' || 'danger' }}",
                "text": "Workflow: ${{ github.workflow }}"
              }]
            }
```
Store the webhook URL as a repository or org secret named `SLACK_WEBHOOK_URL`.

## Gotchas
- `if: always()` ensures the notification fires even when previous steps fail.
- Incoming Webhooks are simpler than OAuth tokens; use them for one-way notifications.
- Slack Block Kit payloads offer richer formatting than legacy `attachments`.
- Rate limit: Incoming Webhooks allow 1 message per second per app.

## Related
- `github-actions-notify-teams.md`
- `github-actions-environment-protection.md`
