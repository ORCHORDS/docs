# github-actions-notify-teams

**Issue:** Sending Microsoft Teams notifications from GitHub Actions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Organisations using Microsoft Teams need CI/CD status notifications delivered to channels without leaving Teams.

## Pattern / Solution
Using a Teams Incoming Webhook (Workflows connector):
```yaml
      - name: Notify Teams
        if: failure()
        uses: jdcargile/ms-teams-notification@v1.4
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          ms-teams-webhook-uri: ${{ secrets.TEAMS_WEBHOOK_URI }}
          notification-summary: "Build failed on ${{ github.ref_name }}"
          notification-color: "FF0000"
          timezone: America/New_York
```
Direct `curl` approach:
```yaml
      - run: |
          curl -H "Content-Type: application/json" \
               -d '{"text":"Build **${{ job.status }}** for `${{ github.repository }}`"}' \
               "${{ secrets.TEAMS_WEBHOOK_URI }}"
```

## Gotchas
- Microsoft retired the legacy Office 365 Connector in August 2024; use the new Workflows (Power Automate) webhook URL.
- Workflows webhooks have a different payload schema — use Adaptive Cards format.
- Store the webhook URI as a secret; it is effectively a secret endpoint.
- Teams throttles to ~4 messages per second per webhook.

## Related
- `github-actions-notify-slack.md`
