# MCP logging-notification data minimization

**Issue:** MCP servers can send log notifications at negotiated levels, creating a channel for secrets, prompts, tool data, or unbounded volume.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Default to minimal level, redact at source, cap rate/size, separate audit from debug, let clients raise/lower level explicitly.

## Tests

Malicious multiline logs, secrets, huge rate, unsupported level, reconnect, disabled logging.

## Gotchas

Log level is not a data-classification control and clients may persist messages.

## Official sources

- https://modelcontextprotocol.io/specification/2025-06-18/server/utilities/logging
