# Node.js test module-mock boundaries

**Issue:** Module mocks installed after an import do not affect existing references, and experimental loader behavior can make ESM and CommonJS tests diverge.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Use the per-test mock tracker, install mock.module before importing the subject, and dynamically import after registration. Pin a Node release and the required experimental flag. Define exports deliberately for ESM, CommonJS, JSON, and built-ins; restore mocks and isolate module caches so sibling tests cannot inherit behavior. Prefer dependency injection when loader-level replacement is unnecessary.

## Verification

Test imports before and after mocking, cache true and false, default plus named exports, require and import parity, JSON modules, restore, concurrent tests, and customization hooks. Run one integration case without mocks.

## Gotchas

- Pin and verify exact platform versions before rollout.
- Preserve reproducible diagnostics without secrets or personal data.
- Define rollback and stop conditions before production use.

## Official source

- [Primary documentation](https://nodejs.org/api/test.html#mockmodulespecifier-options)
