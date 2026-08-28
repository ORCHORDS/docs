# Command Execution Input Separation

Avoid constructing operating-system commands from untrusted strings. Prefer direct APIs and argument arrays, allowlist required values, and isolate execution privileges when command invocation is unavoidable.

Sources: OWASP OS Command Injection Defense Cheat Sheet.