# Session ID Rotation Boundaries

Rotate session identifiers when authentication state or privilege meaningfully changes, including login, privilege elevation, sensitive recovery, and major identity transitions. Avoid carrying a pre-authentication identifier into an authenticated session.

Record rotation expectations in tests and session middleware requirements.

Sources: OWASP Session Management Cheat Sheet.