# sentry-releases

**Issue:** Creating Sentry releases to correlate deployments with error spikes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
After a deploy, error volume increases but it's not clear which commit introduced the regression.

## Pattern / Solution
```bash
# In CI/CD pipeline after build, before deploy
VERSION=$(git rev-parse --short HEAD)

# Create release
sentry-cli releases new $VERSION --org my-org --project my-project

# Associate commits
sentry-cli releases set-commits $VERSION --auto --org my-org

# After deploy completes
sentry-cli releases deploys $VERSION new \
  --env production \
  --org my-org \
  --project my-project
```

GitHub Actions:
```yaml
- uses: getsentry/action-release@v1
  env:
    SENTRY_AUTH_TOKEN: ${{ secrets.SENTRY_AUTH_TOKEN }}
    SENTRY_ORG: my-org
    SENTRY_PROJECT: my-project
  with:
    environment: production
    version: ${{ github.sha }}
```

## Gotchas
- `--auto` for set-commits requires the git repo to be accessible and linked to Sentry
- Finalize release before marking deploy to avoid out-of-order events
- Release names must be unique; use commit SHA or semver

## Related
- `sentry-sourcemaps-upload.md`
- `sentry-error-tracking.md`
- `deployment-event-tracking.md`
