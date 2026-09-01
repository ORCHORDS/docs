# Agent MCP Elicitation Consent Boundary

MCP elicitation lets a server ask the human behind the client for information mid-conversation: `elicitation/create` in form mode collects structured data through the client UI, while URL mode sends the user to an external page for secrets and third-party authorization. Because the server, not the user, initiates the interaction, elicitation is a consent boundary, not a convenience feature. A server that can freely phrase questions, choose form fields, or propose URLs can phish, harvest data, or push the user toward attacker-chosen flows. This article defines when a client should surface an elicitation, what it must disclose, and how it must preserve the user's ability to say no.

## Scope

Applies to MCP clients and hosts that declare the `elicitation` capability (form mode, URL mode, or both) and to the policies they enforce before showing anything to the user. Server-side handling of elicitation state and identity binding is referenced only where it constrains client behavior. Ordinary tool approval prompts and MCP client-to-server OAuth are out of scope; elicitation is explicitly not the mechanism for authorizing the client's own access to the server.

## Workflow or implementation guidance

1. Capability gating first. Before displaying any request, confirm the server is allowed to elicit at all in this session: is the server user-pinned, admin-approved, or first-connect? Record which modes the client declared; a request using a mode the client did not declare is a protocol violation and should return `-32602` rather than render.
2. Normalize and inspect the request before display. Form mode requests must carry a `message` and a `requestedSchema` limited to flat primitive properties; reject or mask schema features outside that restricted subset rather than rendering them raw. URL mode requests must carry a `mode` of `url`, a valid `url`, and an `elicitationId`; anything else is dropped with an error.
3. Show attribution unambiguously. The UI must name which server is asking, using the identity the client verified at connection time, not a display string the server supplied in the request.
4. Disclose the data being requested field by field, with the schema's titles and descriptions shown as untrusted labels: the server wrote them, so they must never be styled as client-generated UI text. Flag fields whose format suggests secrets (`password`, token-like patterns) even though the specification forbids servers from requesting them via form mode.
5. For URL mode, display the full URL with the registrable domain highlighted, check for homoglyph or Punycode look-alikes, and require explicit consent before any navigation. Never pre-fetch the URL or its metadata, and open it in a context the client cannot inspect, not an embedded web view the client controls.
6. Preserve refusal as a first-class outcome. The three-action model maps to distinct UI affordances: accept, decline, and cancel. Decline and cancel must always be available, must require no more effort than accept, and must be honored without punitive retries.
7. Rate-limit and dampen loops. Repeated elicitations, or a `URLElicitationRequiredError` cycle that keeps demanding the same `elicitationId`, triggers a backoff and eventually surfaces a "stop this server" control rather than another dialog.
8. Bind the outcome conservatively. On accept, send exactly the validated content; on decline or cancel, send the action with no content. Never let the agent model answer an elicitation on the user's behalf or pre-fill consent.
9. Log each elicitation: server identity, mode, message digest, schema digest (not the raw labels), URL host for URL mode, action taken, and latency. Do not log submitted field values beyond what privacy policy allows.

## Controls

- A per-server elicitation policy: allowed modes, allowed form-field formats, blocklist for URL destination categories, and a hard cap on elicitations per task.
- Consent display requirements codified in the client: server attribution, per-field disclosure, refusal affordances, and domain highlighting are tested UI contracts, not developer discretion.
- Form mode responses validated client-side against the requested schema before sending, with server-side re-validation expected per the specification.
- Deny-by-default for background or headless sessions: elicitations cannot be auto-accepted by an unattended agent; they queue or fail with a clear reason.

## Validation evidence

- UI tests proving attribution is present and correct for pinned, approved, and unknown servers, including a malicious server that sets a misleading `message`.
- Negative tests: schema with nested objects or undocumented types, URL mode request with an invalid or non-HTTPS URL, missing `elicitationId`, and requests for modes beyond declared capabilities; each must be rejected without display.
- Red-team exercises covering phishing flows: a URL designed to look like a trusted domain, and the account-takeover pattern where one user's elicitation URL is clicked by another; verify the client at minimum does not assist the flow and documents server identity for incident response.
- Telemetry showing decline and cancel rates, repeat-elicitation frequencies, and zero auto-accepts in unattended mode.

## Failure modes and correction

- Dialog fatigue: users rubber-stamp every elicitation. Correction: coalesce repeated requests, make refusals persistent per server, and add a cooling-off period after a burst of elicitations.
- Schema-label spoofing: the server labels a field "Confirm your password" while the client renders it as trusted chrome. Correction: style server-provided labels as untrusted content and block secret-format fields outright.
- Accept treated as completion in URL mode: `action: accept` only means the user consented to open the URL, not that the out-of-band step succeeded. Correction: the client's state machine tracks `notifications/elicitation/complete` separately and never assumes success on accept.
- A canceled dialog is retried immediately by the server, creating a loop. Correction: client-side suppression keyed on request pattern plus the rate-limit control above.

## Limitations

The client cannot verify what happens after a URL-mode navigation; out-of-band interactions are outside its visibility by design, so phishing defense ultimately depends on the server binding elicitations to verified user identity. Form-mode disclosure quality degrades when users cannot evaluate what a field means. Elicitation policy cannot compensate for a server that lies about why it needs data; it can only make the ask visible and refusable. Finally, specification evolution in URL mode means clients should track protocol versions and re-run this validation when adopting new revisions.

## Canonical sources

- Model Context Protocol specification, Client Elicitation: https://spec.modelcontextprotocol.io/specification/2025-11-25/client/elicitation
- Model Context Protocol specification, Security Best Practices: https://spec.modelcontextprotocol.io/specification/2025-11-25/basic/security_best_practices
- OWASP, LLM Top 10 for LLM Applications (LLM06 Sensitive Information Disclosure): https://genai.owasp.org/llm-top-10/
