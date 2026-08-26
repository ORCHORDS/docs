# Node.js package discovery API boundaries

**Issue**

`module.findPackageJSON()` locates package metadata for a specifier, but its result is not a complete or authoritative replacement for module format resolution.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use the API only for discovery and parse returned JSON defensively.
- Do not infer module format solely from a package `type` field; follow Node's documented loader behavior.
- Validate file containment and package identity before using metadata for policy.
- Pin Node because the API and resolution interactions evolve.

## Verification

1. Test bare, relative, absolute, built-in, and invalid specifiers.
2. Exercise nested packages, exports maps, symlinks, and custom hooks.
3. Compare policy decisions with actual import and require behavior.

## Gotchas

- A nearest package file may not govern every resolved file.
- Custom hooks can affect resolution.
- Package metadata is repository-controlled input.

## Official source

- [Official documentation](https://nodejs.org/api/module.html#modulefindpackagejsonspecifier-base)
