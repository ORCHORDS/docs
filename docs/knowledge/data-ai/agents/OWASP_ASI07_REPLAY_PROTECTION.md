# Inter-Agent Replay Protection

## Purpose

Control profile for **OWASP ASI07: Insecure Inter-Agent Communication**.

## Control

Protect security-sensitive agent messages with freshness data such as nonce, request identifier, sequence, or bounded timestamp and reject duplicate use.

## Validation

Replay identical valid requests within and outside the acceptance window; verify side effects do not execute twice.

## Failure correction

Invalidate replayed authorization, reconcile duplicate side effects, and add idempotency or freshness enforcement at the receiver.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://a2a-protocol.org/dev/specification/
- https://www.rfc-editor.org/rfc/rfc9421
