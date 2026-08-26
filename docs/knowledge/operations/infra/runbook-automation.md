# runbook-automation

**Issue:** Converting manual runbook steps into automated remediation to reduce MTTR
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
On-call engineers follow the same manual runbook steps for recurring incidents. Automation exists in heads but not in code. MTTR limited by human availability at 3 AM.

## Pattern / Solution
Runbook automation tiers:
```
Tier 0 — Fully automated (no human needed):
  Alert fires → auto-remediation Lambda → resolved
  e.g. restart crashed pod, scale up ASG, clear SQS DLQ

Tier 1 — One-click (human approval, system executes):
  Alert fires → Slack message with [Remediate] button
  e.g. failover to read replica, drain and replace node

Tier 2 — Guided (step-by-step instructions, human executes):
  Alert fires → Incident channel with runbook link
  For high-risk operations that need human judgment
```

AWS Systems Manager Automation (Tier 0/1):
```yaml
# SSM Automation document
schemaVersion: '0.3'
description: Restart unhealthy ECS tasks
parameters:
  ServiceName:
    type: String
  ClusterName:
    type: String
mainSteps:
- name: RestartUnhealthyTasks
  action: aws:executeScript
  inputs:
    Runtime: python3.11
    Handler: restart_tasks
    Script: |
      import boto3
      def restart_tasks(events, context):
          ecs = boto3.client('ecs')
          tasks = ecs.list_tasks(
              cluster=events['ClusterName'],
              serviceName=events['ServiceName'],
              desiredStatus='STOPPED'
          )['taskArns']
          ecs.update_service(
              cluster=events['ClusterName'],
              service=events['ServiceName'],
              forceNewDeployment=True
          )
```

PagerDuty → Slack → automation trigger:
```python
# Slack app listening for button interaction
@app.action("remediate_db_connections")
def handle_remediation(ack, body, client):
    ack()
    incident_id = body['actions'][0]['value']
    # Trigger SSM automation or Lambda
    ssm.start_automation_execution(
        DocumentName='RestartUnhealthyTasks',
        Parameters={'ServiceName': ['api'], 'ClusterName': ['prod']}
    )
    client.chat_postMessage(channel=body['channel']['id'],
                            text=f"Remediation triggered for incident {incident_id}")
```

## Gotchas
- Auto-remediation must not mask the root cause — log every automated action for post-mortem
- Circuit breaker: after N automated remediations in M minutes, stop and page a human
- Test automated runbooks in staging — a broken automation during incident makes things worse
- Permission scope for automation roles must be minimal — a bug could amplify blast radius

## Related
- `incident-war-room-setup.md`
- `toil-reduction-sre.md`
- `post-mortem-blameless-template.md`
