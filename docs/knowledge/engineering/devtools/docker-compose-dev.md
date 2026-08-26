# docker-compose-dev

**Issue:** Local development services not containerized consistently
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Developers install Postgres globally at different versions; services conflict or are not reproducible.

## Pattern / Solution
docker-compose.yml defines dev services. Use docker compose up -d for background start. Mount volumes for data persistence. Override with docker-compose.override.yml for local customizations (not committed). Health checks ensure service readiness.

## Gotchas
- docker-compose.override.yml is automatically merged — document this for new devs
- Volume names include project prefix; name explicitly to avoid orphan volumes

## Related
- docker-desktop-setup, devcontainer-json, dotenv-local-setup
