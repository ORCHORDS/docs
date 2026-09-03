# Goal Checkpoint Revalidation

## Purpose

Control profile for **OWASP ASI01: Agent Goal Hijack**.

## Control

Revalidate the task goal before high-impact stages such as external publication, money movement, destructive writes, credential use, or broad data export.

## Validation

Inject goal-changing context immediately before each protected stage and verify the stage rechecks current intent rather than relying on an earlier approval.

## Failure correction

Stop the action, invalidate stale approvals, and move the checkpoint closer to the irreversible operation if the gap allowed unsafe execution.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://genai.owasp.org/resource/agent-control-standard-acs/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
