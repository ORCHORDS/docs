# Cookie and Session Support Diagnosis

## Purpose and scope

Use this runbook for browser session loss. Its goal is to turn a customer symptom into safe, reproducible evidence and a bounded request to the team that owns the failing component. It does not replace engineering investigation, incident command, legal review, or a product service commitment.

Record the affected account through approved verification, requested outcome, business impact, first observed time, frequency, environment, and last known success. Use UTC for system events while retaining the customer's stated local time and offset. Collect only information necessary to diagnose this case.

## Intake and diagnosis

Capture origin, navigation sequence, cookie attributes without values, cross-site context. Preserve exact machine output instead of paraphrasing it. The topic-specific control is to test SameSite, Secure, Domain, Path, expiry, and credentials mode separately. Never request passwords, private keys, session cookies, bearer credentials, payment data, or an unrestricted production dataset. Redact unrelated personal and proprietary material before attachment.

Create the smallest safe reproduction. Identify the precise component and supported path, then run a baseline with a controlled account or test object. Record inputs, tool and version, expected result, actual result, timestamp, and correlation identifier. Change one variable at a time and preserve both passing and failing results. Do not run a test that can charge an account, send a message, change production state, or weaken security without owner approval.

Classify observations as configuration, client behavior, network or protocol behavior, service defect, security concern, documentation gap, or unknown. Unknown is acceptable while evidence is incomplete. Separate customer statements, agent observations, system records, and hypotheses in the timeline. Similar symptoms do not establish a common root cause.

## Resolution workflow

1. Confirm scope, environment, affected operation, and ownership boundary.
2. Check current official documentation, service telemetry, configuration history, deployments, and status records.
3. Compare the failure with a known-good control using the same measurement method.
4. Apply only a documented correction or reversible workaround. Record its owner, side effects, expiry, and rollback.
5. Escalate with impact, chronology, sanitized artifacts, reproduction status, comparisons, and one explicit technical question.
6. Repeat the original operation and a boundary or negative test. Confirm the customer's business outcome, not just disappearance of an error.

Caches, asynchronous jobs, retries, and distributed systems can make one successful attempt misleading. Wait the documented interval, use a new correlation identifier, and validate at the protocol or artifact level. A screenshot can support context but should not replace structured logs or wire-level results where those are available.

## Controls and evidence

Restrict access according to sensitivity. Store large or sensitive artifacts in the approved evidence repository and link them from the case. Record the collector, source, collection time, and every redaction or transformation. Hash downloaded artifacts when integrity matters. Follow retention, deletion, and legal-hold requirements.

The closure record must include impact, chronology, raw error, environment versions, reproduction, approved actions, handoffs, workaround status, and validation. Useful quality checks include evidence completeness, escalation rework, recurrence, and workaround age. Metrics must not reward premature closure.

## Failure handling

If evidence is unavailable, name the missing item, explain why it matters, and propose the safest next test. Offer an accessible guided collection method when the customer cannot perform technical steps. Stop testing and invoke incident management if impact grows. Route indicators of unauthorized access, abuse, or sensitive-data exposure immediately through security or privacy channels without conducting an unapproved investigation.

Rollback a failed workaround where possible. Keep or reopen the case when validation is inconclusive. Closure requires the customer-visible result, remaining limitations, linked defect or problem record, and follow-up owner. No customer response may permit administrative closure under policy, but is never evidence of technical recovery.

## Canonical sources

- [https://www.rfc-editor.org/rfc/rfc6265](https://www.rfc-editor.org/rfc/rfc6265)
- [https://fetch.spec.whatwg.org/](https://fetch.spec.whatwg.org/)

## Scope note

Standards define interoperable behavior, not every product configuration. Product steps must cite current official owner documentation.
