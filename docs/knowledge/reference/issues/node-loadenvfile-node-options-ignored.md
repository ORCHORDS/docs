# Node loadEnvFile ignores NODE_OPTIONS

**Issue:** Node process.loadEnvFile loads dotenv variables but NODE_OPTIONS in that file has no effect, causing config assumptions to diverge.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Validate required variables after load, configure runtime flags at process launch, keep precedence explicit and never store secrets in committed dotenv.

## Tests

NODE_OPTIONS present, duplicate vars, missing file, malformed lines, alternate cwd, inherited env.

## Gotchas

Successful load does not mean every key affected Node startup.

## Official sources

- https://nodejs.org/api/process.html#processloadenvfilepath
