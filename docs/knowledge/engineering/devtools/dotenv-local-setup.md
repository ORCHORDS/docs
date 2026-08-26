# dotenv-local-setup

**Issue:** Local environment variables not managed, secrets committed accidentally
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Developers edit .env directly, then accidentally commit secrets. Or .env.example drifts from actual vars.

## Pattern / Solution
Commit .env.example with all keys, empty values. .env.local (gitignored) holds actual local values. Use dotenv-vault or infisical for team secret sync. CI uses secrets manager. Keep .env.example updated in PRs that add new vars.

## Gotchas
- Never commit .env to version control — add to .gitignore immediately
- dotenv-expand needed if you use variable interpolation

## Related
- direnv-env-setup, docker-compose-dev
