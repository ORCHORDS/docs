# Hotfix Process

## Overview
A hotfix process ensures rapid deployment of critical fixes while maintaining system stability and quality standards. This structured approach minimizes risk while addressing urgent production issues.

## Triage Process
When a critical issue is reported, immediately assess severity using the severity gate criteria:
- **S1**: System down, data loss, security breach - deploy immediately
- **S2**: Major functionality broken, severe performance impact - deploy within 2 hours
- **S3**: Minor functionality issues, user experience problems - deploy within 24 hours

Document the issue with clear reproduction steps, affected systems, and impact assessment. Assign priority level and notify relevant stakeholders.

## Bypass CI Requirements
For urgent hotfixes, bypass standard CI pipeline when:
- Critical system outage requires immediate resolution
- Issue cannot be reproduced in staging environment
- Time constraints exceed normal testing windows

**Required bypass approvals**: Lead developer, QA manager, and operations manager must sign off before proceeding. Document the rationale for bypassing CI.

## Cherry-Pick to Production
1. Create hotfix branch from stable release tag
2. Apply minimal fix without introducing new features
3. Test locally with production-like environment
4. Merge to main branch via pull request with explicit hotfix label
5. Deploy to production using automated deployment pipeline
6. Verify fix in production environment

## Post-Hotfix Review
Conduct comprehensive review within 48 hours:
- Validate fix effectiveness and regression testing results
- Document lessons learned and process improvements
- Update monitoring alerts for similar issues
- Schedule follow-up meeting with team to discuss root cause analysis
- Create permanent fix for next release cycle

## Communication Protocol
Notify stakeholders immediately upon hotfix initiation:
- **Internal**: Team members, QA, operations, product managers
- **External**: Customers (if applicable), support teams
- **Status updates**: Every 2 hours during deployment window
- **Resolution confirmation**: Final notification when fix verified in production

## Severity Gate Criteria
Establish clear severity thresholds for hotfix approval:
- **S1**: Critical system failure requiring immediate attention
- **S2**: Major functionality degradation affecting core users
- **S3**: Minor issues impacting user experience or minor features
- **S4**: Non-critical enhancements or documentation updates

## Checklist
- [ ] Issue triaged and severity assessed
- [ ] Bypass CI approval obtained
- [ ] Hotfix branch
