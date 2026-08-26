# clickup-engineering

**Issue:** ClickUp configuration not optimized for engineering team workflow
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Engineers do not use ClickUp because the setup does not match software development workflow.

## Pattern / Solution
Create dedicated Engineering space. Use Sprints view for iteration planning. Custom fields: Story Points, PR Link, Environment. GitHub integration for PR-to-task linking. Automations: move task to In Review when PR opened, Done when merged.

## Gotchas
- ClickUp's power comes from customization but excessive custom fields create form fatigue
- Automation quota limits on lower tiers — prioritize high-value automations

## Related
- linear-issue-workflow, jira-engineering-workflow
