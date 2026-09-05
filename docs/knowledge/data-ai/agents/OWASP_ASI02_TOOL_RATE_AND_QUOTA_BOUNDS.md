# Tool Rate and Quota Bounds

## Purpose

Control profile for **OWASP ASI02: Tool Misuse and Exploitation**.

## Control

Set task-appropriate ceilings for tool calls, cost, bytes, recipients, records, and other scalable side effects to contain misuse even when individual calls look valid.

## Validation

Drive repeated valid calls until each configured limit is reached and verify further execution fails predictably.

## Failure correction

Cancel the runaway task, reconcile side effects and cost, and reduce or partition quotas if the existing bound allowed excessive impact.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://blog.modelcontextprotocol.io/posts/2026-07-28/
- https://genai.owasp.org/resource/agent-control-standard-acs/
