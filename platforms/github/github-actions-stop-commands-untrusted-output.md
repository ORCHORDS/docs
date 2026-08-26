# Suspend GitHub Actions Workflow Commands Around Untrusted Output

**Issue:** GitHub Actions runners interpret workflow-command syntax written to standard output. Dumping untrusted files or tool output can accidentally create annotations or invoke other command handling.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Prefer artifact upload or escaped, structured summaries over printing untrusted bulk content.
- When raw output is necessary, issue `::stop-commands::{token}` first and resume with the same token afterward.
- Generate a cryptographically unpredictable token unique to each run; never use a constant or attacker-derived marker.
- Place suspension and resumption in the same tightly scoped step and ensure error handling restores command processing when later commands are required.
- Continue masking secrets and minimizing logs; stopping commands is not secret redaction.
- Pass outputs and environment values through the designated environment files rather than legacy stdout commands.

## Verification

- Feed output containing command-like lines and assert they are rendered literally while processing is suspended.
- Attempt to guess or inject the resume marker and ensure it fails.
- Test shell failure and cancellation paths so command state cannot surprise later logic in the same step.
- Review logs for secrets independently of workflow-command tests.

## Gotchas

The resume token appears in the log protocol, so uniqueness—not secrecy after use—is the essential property. Suspension affects workflow-command parsing, not shell interpretation, artifact safety, or terminal escape sequences.

## Official sources

- [GitHub Actions workflow commands](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands#stopping-and-starting-workflow-commands)
