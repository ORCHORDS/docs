# act-github-actions-local

**Issue:** GitHub Actions workflows take minutes to debug via push-and-wait cycle
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Every workflow change requires a commit and push, waiting minutes for CI to run.

## Pattern / Solution
act runs GitHub Actions workflows locally using Docker. act -j build runs a specific job. Uses act pull policy to manage runner images. Set secrets via .secrets file. Supports matrix builds and environment variables.

## Gotchas
- act uses Docker containers that differ from actual GitHub runners — some actions fail locally
- Large runner images (ubuntu-latest) are multi-GB; use nektos/act-environments-ubuntu:18.04 for lighter image

## Related
- github-cli-daily-workflow, docker-desktop-setup, makefile-developer-tasks
