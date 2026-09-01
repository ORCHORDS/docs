# Function Call Argument Hardening Under the OWASP API Security Top 10

## Scope

When an agent emits a function call, the model has produced a structured argument set that crosses a trust boundary into a system that performs an effect. That crossing is an API call, and the OWASP API Security Top 10 documents the recurring failure patterns for arguments crossing such boundaries: unauthorized object access, broken property-level authorization, unrestricted resource consumption, broken authentication, server-side request forgery, mass assignment, and the rest. These categories map onto agent-emitted function calls with surprising fidelity, because from the downstream system's perspective there is no meaningful distinction between a human-typed call and a model-emitted one.

This article covers argument hardening discipline that treats model-emitted calls with the same rigor as API traffic from any other client. The center of gravity is the boundary where the agent runtime converts model output into an execution request. That boundary is where validation, authorization, and rate limiting belong, and where they must be applied regardless of whether the caller is presented to the downstream system as a human, a service account, or an agent identity.

## Workflow or implementation guidance

1. Enforce an allow-list of argument names for every tool. Reject unknown properties explicitly rather than ignoring them; silent dropping is convenient but hides intent. Use JSON Schema strict modes and runtime guards that treat the allow-list as authoritative.
2. Validate types strictly. Numeric values must be numbers, not numeric strings. Enums must be from the closed set. Arrays must be arrays, and strings must be strings. Coercion across types is the most common source of silent privilege escalation in argument handling.
3. Enforce bounds. Length limits on strings and arrays, range checks on numbers, count limits on collection arguments, and cumulative size limits across the whole call. The OWASP category on unrestricted resource consumption is, in agent settings, usually an argument-size problem before it is a request-rate problem.
4. Normalize before authorization. Resolve references and identifiers to canonical internal forms so authorization decisions see the same shape regardless of whether the model wrote `user_42` or `usr-42` or `users/42`. Then authorize against that canonical form, not against the raw text.
5. Authorize at the property level, not only at the object level. The OWASP category on broken object property-level authorization exists because too many APIs check that the caller can see the object but then return or accept every property of it. Agent arguments frequently include optional fields for sensitive sub-objects, and the same discipline applies on the write path.
6. Block server-side request forgery by refusing argument values that contain URLs or identifiers resolvable into outbound network operations unless the tool's purpose explicitly requires it, and then resolving them through an egress allow-list rather than letting the value directly determine the destination.
7. Reject mass assignment. Whitelist which fields a tool call is permitted to set on a resource; refuse the rest. The OWASP category names mass assignment for relational frameworks, but the same pattern shows up in JSON argument handlers where a structured blob carries the entire resource update.
8. Strip or reject non-text where the schema forbids it. Mark-up, control characters, and unexpected encodings are not the model's job to defend against and should be removed before arguments reach the tool.

## Controls

Per-tenant and per-tool rate limits are necessary but not sufficient. Pair them with cumulative budget controls across an entire session so a long-running agent cannot amortize a denial-of-service into hundreds of small calls. Apply cost-based limits where the downstream system bills per call, since monetary harm is a real outcome here even when the response is fast.

Authentication of the agent itself is a separate control from argument validation. A call that fails argument validation should not propagate as an authentication failure unless authentication was actually attempted. Record authentication failures distinctly from validation failures so trends remain interpretable; merging the two masks both signal types.

Authorize explicitly. Many framework defaults assume an authenticated caller may modify any field the schema declares, which is the failure mode the OWASP category names. Make the property-level policy explicit per tool, review it on schema change, and treat any policy exception as a temporary override with an expiry and an owner.

## Validation evidence

Test the obvious positives and the recurring negatives. A valid call from a permitted tenant with permitted fields executes, and a valid call from an unpermitted tenant is denied with a stable error. Unknown fields are rejected rather than silently accepted or silently dropped. Mass-assignment attempts fail when an attempt to set a sensitive field is made alongside permitted fields. SSRF attempts where the argument carries a destination fail when the destination is outside the egress allow-list.

Resource consumption tests must be measurable: a deliberate over-limit call returns within the budget and does not consume downstream capacity beyond what the limit implies. Property-level authorization tests must confirm that a caller permitted to read cannot write, and a caller permitted to write cannot read, on the same tool.

Also test the boundary with the model: arguments generated under controlled prompts that attempt to violate each property produce the same outcome as arguments generated by direct API clients. This last test is what distinguishes an agent-aware validation suite from a generic API test suite, and is too often omitted.

## Failure modes and correction

A frequent failure is the missing default deny. A new field is added to a tool schema, the registration system permits it because there is no entry denying it, and downstream code accepts it because it is present. Correct by maintaining explicit allow-lists per tool and treating addition as requiring registration, not as automatic acceptance.

A subtler failure is coercion laundering. The runtime coerces a string into a number, an array of length one into a scalar, or a path into a URL, all in the name of being permissive. Each coercion is a place where a malformed argument can become a privileged one. Correct by removing coercions that lack an explicit, reviewed reason, and by logging remaining coercions so the rate is observable.

When an argument validation failure begins to fire frequently, treat it as a signal rather than noise. Either the schema is out of sync with model behavior, the schema has a bug, or the model is being misled by hostile input. Investigation, not noise suppression, is the right response. Suppressing the error or retrying automatically is the wrong one.

## Limitations

Argument hardening cannot recover information the model never had access to. It does not validate factual claims about the world, and it cannot ensure that a permitted argument corresponds to a state the user actually wanted. JSON Schema cannot express every constraint a domain needs, so runtime checks remain necessary. Per-tool policy maintenance is an ongoing cost that grows with the tool surface, and partial automation will miss edge cases without human review. Finally, hard limits are not free: tight validation can cause legitimate calls to be retried by the model, increasing latency and obscuring cause attribution.

## Canonical sources

- **OWASP API Security Top 10 (2023 edition):** https://owasp.org/API-Security/editions/2023/en/0x11-t10/
- **OWASP, Broken Object Property Level Authorization (API3:2023):** https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/
- **OWASP, Unrestricted Resource Consumption (API4:2023):** https://owasp.org/API-Security/editions/2023/en/0xa4-unrestricted-resource-consumption/
- **OWASP, Broken Authentication (API2:2023):** https://owasp.org/API-Security/editions/2023/en/0xa2-broken-authentication/
