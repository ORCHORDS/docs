# Delegation Audience Binding

## Purpose

Control profile for **OWASP ASI03: Identity and Privilege Abuse**.

## Control

Bind delegated tokens to the intended resource or audience so a credential issued for one service cannot be replayed to another.

## Validation

Present the same delegated credential to intended and unintended resources; verify only the intended audience accepts it.

## Failure correction

Revoke or replace broadly valid tokens, enforce audience validation at resource servers, and retest every delegation path.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.rfc-editor.org/rfc/rfc8707
- https://www.rfc-editor.org/rfc/rfc8693
