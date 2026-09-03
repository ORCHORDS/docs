# Inter-Agent Message Signatures

## Purpose

Control profile for **OWASP ASI07: Insecure Inter-Agent Communication**.

## Control

Use message-level integrity protection where messages can traverse intermediaries, queues, or storage that transport security alone does not cover.

## Validation

Modify protected headers or body fields after signing and verify the receiver rejects the altered message.

## Failure correction

Quarantine the message, correct signing or verification coverage, and rotate signing keys if compromise is suspected.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.rfc-editor.org/rfc/rfc9421
- https://a2a-protocol.org/dev/specification/
