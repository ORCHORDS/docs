# soc2-cc8-change-management

**Issue:** SOC 2 CC8 change management controls for production environments
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
CC8 requires a formal change management process to ensure authorized, tested, and documented changes to infrastructure, software, and configurations.

## Pattern / Solution
Change management workflow:
1. Change request ticket created (Jira/Linear) with: description, risk assessment, rollback plan, test plan
2. Peer review and approval (at minimum one other engineer; high-risk = senior engineer + manager)
3. Change tested in staging environment
4. Deployment via CI/CD pipeline (no manual production changes)
5. Post-deployment verification
6. Change record updated with actual vs. planned outcome

Emergency change procedure:
- Approval from on-call manager via documented channel (Slack DM with screenshot or phone with ticket update)
- Full retrospective ticket within 24 hours
- Emergency changes tracked separately; auditor will review these specifically

Evidence required:
- Pull request approvals (GitHub/GitLab)
- Deployment logs with timestamps and deployer identity
- Staging test results
- Infrastructure-as-code (Terraform/CDK) showing code review gate

Segregation of duties:
- Developer who wrote code cannot be sole approver
- Production deployment access restricted to CI/CD service accounts

## Gotchas
- Database schema changes are change management events — must be tracked
- Configuration changes (environment variables, IAM policies) count as changes
- Hotfix bypass of staging test requires compensating control (immediate prod test + post-change review)
- Auditors compare deployment timestamps to change tickets — gaps or backdated tickets are findings

## Related
- `soc2-cc7-system-operations.md`
- `soc2-evidence-collection-automation.md`
