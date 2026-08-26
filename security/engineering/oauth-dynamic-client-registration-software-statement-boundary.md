# OAuth Dynamic Client Registration Software-Statement Boundary

**Issue:** A dynamic registration endpoint that accepts unsigned metadata beside a software statement can let a registrant replace trusted redirect URIs, contacts, or capabilities unless precedence and issuer trust are enforced.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls
- Validate the RFC 7591 software statement signature, issuer, audience where used, time bounds, and statement identifier against an explicit software-publisher trust policy.
- Apply the rule that valid metadata in the software statement takes precedence over the same metadata supplied as plain JSON in the registration request.
- Validate all effective redirect URIs, grant and response types, authentication methods, names, and extension metadata after precedence is resolved.
- Keep an initial access token used to authorize registration separate from any registration access token issued to manage the resulting client.
- Detect replay or duplicate software instances according to policy and bind audit records to statement issuer, statement identifier, effective metadata, and resulting client ID.
- If RFC 7592 management is enabled, note its Experimental status; scope the registration access token to its client and protect the client configuration URI.

## Verification
- Attempt to override each statement-controlled field in plain JSON and confirm the effective metadata remains trusted.
- Test invalid signature, untrusted issuer, stale statement, duplicate statement, bad redirect URI, and cross-client registration-token use.
- Fetch and update client metadata only with the correct registration access token and confirm secrets never appear in logs.

## Gotchas
A signed statement says an issuer vouched for claims; it is not automatically trusted. Trust policy and effective-metadata validation remain authorization decisions.

## Official sources
- https://www.rfc-editor.org/rfc/rfc7591.html
- https://www.rfc-editor.org/rfc/rfc7592.html
