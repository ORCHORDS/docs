# Secret-bearing jobs define a trust tier

**Lesson:** Runner labels and workflow names do not create isolation. A job that receives signing, cloud, or production credentials belongs to a higher trust tier with separate dispatch and cleanup controls.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Operationalization

Restrict trusted refs and environments, use least privilege and short-lived credentials, isolate runners, and prove cleanup after cancellation.

## Verification

Attempt fork, untrusted dependency, artifact substitution, and prior-job residue access; verify credentials remain unavailable.

## Gotchas

Masking logs is not containment, and environment approval cannot clean a persistently compromised runner.

## Official sources

- https://docs.github.com/en/actions/reference/security/secure-use
