# httpie-patterns

**Issue:** curl commands are verbose and hard to read; need simpler HTTP CLI
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Testing APIs from terminal requires long curl flags; response JSON not formatted.

## Pattern / Solution
http GET api.example.com/users Authorization:Bearer-token. Auto-pretty-prints JSON, adds Content-Type headers. Persistent sessions: http --session=./session.json. xh is Rust alternative with faster startup.

## Gotchas
- http POST url key=value sends JSON; key==value sends as query param
- xh is a drop-in replacement with faster startup for scripts

## Related
- curl-advanced-usage, bruno-api-client, postman-collections
