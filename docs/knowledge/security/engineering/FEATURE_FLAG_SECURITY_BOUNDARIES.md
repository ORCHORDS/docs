# Feature Flag Security Boundaries

Do not treat client-visible feature flags as authorization. Enforce security decisions server-side and consider whether disabled features still expose endpoints, data paths, or privileged operations.

Sources: OWASP Access Control guidance.