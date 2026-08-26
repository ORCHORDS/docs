# Node --run package-script environment boundary

**Issue:** Replacing `npm run` with Node's faster `--run` command without checking semantics can skip lifecycle behavior or select a different ancestor package and tool binary.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Pin a Node version that supports `--run`, and document which scripts may use it. Do not make a repository-wide mechanical substitution for a package-manager command.
- Resolve and log `NODE_RUN_PACKAGE_JSON_PATH` and `NODE_RUN_SCRIPT_NAME` in CI so the selected package and script are auditable.
- Account for upward `package.json` discovery, execution from that package directory, and `PATH` entries prepended from ancestor `node_modules/.bin` directories.
- Keep scripts self-contained; do not depend on npm-specific pre/post lifecycle hooks, environment variables, workspace fan-out, or package-manager policy unless separately invoked.
- Run the same pinned command on every supported shell and operating system.

## Verification

Test from the package root and nested directories, with multiple ancestor package files and binary versions, a missing script, forwarded arguments, nonzero exit, signals, and spaces in paths. Compare environment and side effects with the former package-manager command before changing the authoritative lane.

## Gotchas

- Faster startup does not imply semantic equivalence to `npm run`.
- Ancestor binary lookup can select a tool the leaf package did not declare.
- A successful script can still bypass package-manager workspace ordering or lifecycle policy.

## Official source

- [Node.js command-line API: --run](https://nodejs.org/api/cli.html#--run)
