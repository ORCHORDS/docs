# deployment-approval-workflow

**Issue:** Implementing human approval gates before production deployments
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Automated pipelines that deploy directly to production without human review create risk. Approval gates enforce a deliberate checkpoint while keeping the process fast enough to be followed consistently.

## Pattern / Solution
GitHub Actions environment protection rules:
```yaml
# In GitHub repo settings: Settings > Environments > production
# Required reviewers: [ops-team, release-manager]
# Wait timer: 0 minutes (or 5 for last-minute review)

jobs:
  deploy-production:
    environment:
      name: production
      url: https://myapp.example.com
    runs-on: ubuntu-latest
    needs: [deploy-staging, integration-tests]
    steps:
      - name: Deploy
        run: helm upgrade --install myapp ./chart --set image.tag=$IMAGE_TAG -n production
```

Slack-based approval (using a custom slash command or button):
```python
# Webhook handler for Slack button click
@app.route('/slack/approve', methods=['POST'])
def handle_approval():
    payload = json.loads(request.form['payload'])
    action = payload['actions'][0]['value']
    user = payload['user']['name']

    if action == 'approve':
        # Trigger CI pipeline via API
        requests.post(
            f"{GITHUB_API}/repos/{REPO}/actions/workflows/deploy.yml/dispatches",
            headers={"Authorization": f"token {GH_TOKEN}"},
            json={"ref": "main", "inputs": {"approver": user}}
        )
        return jsonify({"text": f"✅ Approved by {user} — deploying now"})
    else:
        return jsonify({"text": f"❌ Rejected by {user}"})
```

Approval audit log pattern:
```bash
# Record approval in a shared audit table or log
psql $AUDIT_DB -c "
  INSERT INTO deploy_approvals (service, version, approver, approved_at, environment)
  VALUES ('myapp', '$IMAGE_TAG', '$APPROVER', NOW(), 'production');
"
```

Change freeze enforcement:
```bash
# In CI script — check freeze calendar
FREEZE=$(curl -s "$DEPLOY_API/freeze/active" | jq -r '.active')
if [ "$FREEZE" = "true" ]; then
  echo "🚫 Deployment freeze active. Aborting."
  exit 1
fi
```

## Gotchas
- Approval steps that timeout silently allow the deployment to proceed — always configure explicit timeout + failure behavior
- Approvers should not approve their own changes; enforce this in the CI platform or via policy
- Approval audit logs are required for SOC 2 and ISO 27001 compliance; do not rely on CI logs alone
- "Soft" approval gates (warnings only) are ignored under pressure; make them hard blocks

## Related
- `deployment-notification-slack.md`
- `deployment-freeze-policy.md`
- `cab-change-management.md`
- `deployment-window-management.md`
