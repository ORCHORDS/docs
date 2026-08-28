# Path Traversal Canonicalization

Resolve and validate filesystem paths against an intended root before access. Avoid trusting filename sanitization alone; canonicalize paths, constrain directories, use generated storage names, and keep application permissions narrow.

Sources: OWASP Path Traversal guidance.