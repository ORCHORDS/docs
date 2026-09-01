---
title: "OWASP MASTG 2.0 Test Evidence"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# OWASP MASTG 2.0 Test Evidence

## Pinned source and scope
OWASP MASTG **2.0.0**, released 30 June 2026. This article uses the named version and identifiers; do not combine evidence from another edition without a migration record.

## Control interpretation
MASTG 2.0 organizes test cases with stable MASTG-TEST identifiers and links them to MASVS controls. Pin both the MASTG test ID and revision because techniques evolve. A tool invocation is not a test result: prerequisites, observation, interpretation, and control mapping are required.

## Domain-specific procedure
For each case record app package/bundle ID, binary hash, build type, signing identity, OS/device, lock/root/jailbreak state, accounts, proxy, tools and versions, commands, sanitized raw output, expected outcome, actual outcome, MASVS mapping, and analyst conclusion. Repeat static and dynamic observations on release-equivalent builds and supported OS versions. Mark Not Tested and Not Applicable distinctly from Pass.

## Evidence and decision
Each result must preserve its MASTG-TEST ID, app hash, device state, commands, raw observation, expected result, interpretation, and MASVS mapping. Another analyst must be able to repeat it.

## Failure modes
Screenshots without commands, debug-build-only results, “not observed” marked Pass, and a tool version omitted from evidence are invalid.

## Sources
- [Pinned canonical source](https://github.com/OWASP/owasp-mastg/releases/tag/v2.0.0)
