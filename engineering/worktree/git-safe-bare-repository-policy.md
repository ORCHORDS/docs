# Git safe bare-repository policy

**Issue**

Implicit discovery of bare repositories can make commands operate on an unintended repository in attacker-controlled directories.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Set `safe.bareRepository` according to the execution environment.
- Pass explicit `--git-dir` for approved bare repositories.
- Keep global/system config protected from workflow writes.

## Verification

1. Place bare repositories in parent directories and test discovery.
2. Run explicit and implicit commands.
3. Verify CI wrappers fail closed.

## Gotchas

- Policy is config-scope sensitive.
- Bare repository safety differs from safe.directory.
- Explicit paths still require authorization.

## Official source

- [Official documentation](https://git-scm.com/docs/git-config#Documentation/git-config.txt-safebareRepository)
