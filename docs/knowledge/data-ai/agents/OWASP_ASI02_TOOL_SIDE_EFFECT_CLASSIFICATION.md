# Tool Side-Effect Classification

## Purpose

Control profile for **OWASP ASI02: Tool Misuse and Exploitation**.

## Control

Classify tools and operations by side effect such as read, write, publish, delete, execute, transfer, or administer, then bind stronger controls to higher-impact classes.

## Validation

Compare tools with similar names but different side effects and verify policy follows the operation's effect rather than its label.

## Failure correction

Correct catalog metadata, invalidate cached capability descriptions, and review prior executions that used the wrong classification.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://blog.modelcontextprotocol.io/posts/2026-07-28/
- https://genai.owasp.org/resource/agent-control-standard-acs/
