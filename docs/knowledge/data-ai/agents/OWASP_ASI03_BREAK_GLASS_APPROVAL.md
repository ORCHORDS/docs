# Break-Glass Privilege Approval

## Purpose

Control profile for **OWASP ASI03: Identity and Privilege Abuse**.

## Control

Treat emergency privilege elevation as a separate, time-limited, strongly audited path with explicit approval and automatic expiry.

## Validation

Request emergency access without approval, after expiry, and outside the declared incident context; verify all are denied.

## Failure correction

End the elevated session, rotate temporary credentials, review every action taken, and correct approval or expiry enforcement gaps.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.rfc-editor.org/rfc/rfc9700
- https://genai.owasp.org/resource/agent-control-standard-acs/
