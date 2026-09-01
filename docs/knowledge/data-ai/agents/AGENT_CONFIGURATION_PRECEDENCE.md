# Configuration Precedence and Safe Overrides for Agents

## Scope

Agent behavior is assembled from defaults, deployment settings, tenant policy, task parameters, tool metadata, and model-produced suggestions. If precedence is implicit, an untrusted field can override a safety limit or two replicas can execute the same task differently. This article defines a typed configuration merge with explicit authority. It is not prompt-instruction design and does not cover model replacement or general change control.

NIST SP 800-53 configuration-management controls emphasize baselines, controlled changes, least functionality, and monitoring. OWASP guidance on secure configuration and authorization reinforces deny-by-default and server-side enforcement. The agent-specific requirement is to make every effective value explainable by source and to prevent lower-authority inputs from weakening higher-authority constraints.

## Workflow

1. Define a schema for every configurable field, including type, unit, allowed range, sensitivity, mutability, and merge operator.
2. Assign sources to trust tiers: compiled safety floor, organization policy, environment baseline, tenant policy, authenticated request, tool declaration, and model suggestion. A model suggestion is data, not authority.
3. Parse each source independently with strict unknown-field rejection for security-relevant namespaces. Normalize units and identifiers before merging.
4. Apply field-specific merge rules. For ceilings use the minimum permitted value; for required control sets use union; for allowlists use intersection; for immutable identifiers permit exactly one authoritative source. Avoid generic “last writer wins.”
5. Validate cross-field invariants after merge, such as deadline not exceeding lease, enabled tool requiring an authorization policy, and retry count fitting the run budget.
6. Produce an immutable effective-configuration snapshot and a provenance map identifying the winning or constraining sources.
7. Bind the snapshot digest to the run before execution. Children inherit it or receive an explicitly narrower derived snapshot.
8. Reject mid-run mutation unless the field is declared dynamic and the transition is atomic, audited, and safe for already-started operations.

## Controls, data, and evidence

Keep safety floors outside tenant-controlled stores. Sign or otherwise integrity-protect deployed baselines according to the platform threat model. Restrict who can publish each source and separate proposal from approval for sensitive changes. Validate environment variables and command-line inputs just as strictly as remote configuration.

The provenance record should include field path, normalized effective value or protected digest, source identifiers, source revisions, merge operator, constraints applied, validation result, snapshot digest, and activation time. Secrets should be referenced, not copied into provenance. Evidence includes schema reviews, source-authority matrices, approval records, reproducible merge tests, rejected override samples, and fleet checks proving all replicas resolved the expected digest.

## Validation tests

Attempt to increase a hard token ceiling from tenant settings, request metadata, a tool result, and model output; each must remain constrained. Verify a tenant can lower its own limit where permitted. Test allowlist intersection so a lower tier cannot add a tool absent from organization policy. Supply unknown fields, duplicate keys, wrong units, integer overflow, null values, and ambiguous booleans.

Reorder source documents and confirm the same effective snapshot because precedence is explicit rather than parser order. Start two replicas with the same revisions and compare digests. Change a dynamic kill switch during a run and verify atomic visibility; change an immutable tool policy and verify it applies only through the documented restart or new-run path. Property-test monotonicity: adding a lower-authority constraint may narrow behavior but cannot broaden it.

## Failure handling

If a required source is unavailable, use a previously approved, unexpired snapshot only when policy allows; otherwise reject new runs. Do not silently fall back to permissive defaults. If sources conflict on an immutable field, fail configuration resolution and identify both authorities without leaking secret values.

When fleet digests diverge, stop scheduling affected workload classes, preserve snapshots, and restore a known approved baseline. If an unsafe override was accepted, disable the relevant capability, identify runs bound to the bad digest, and handle resulting actions through incident procedures. Rollback itself must pass current safety floors; an old configuration is not automatically safe.

## Limitations

Explicit precedence cannot prove that policy values are wise or that publishers are trustworthy. Complex field-specific merges increase implementation and review burden. Some values interact non-monotonically, requiring a full invariant solver or rejection rather than merging. Dynamic configuration introduces race conditions that snapshots only partly address. This control also does not protect code paths that bypass the resolved snapshot.

## Canonical sources

- **NIST, SP 800-53 Revision 5, Configuration Management family:** https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- **NIST, SP 800-128, Guide for Security-Focused Configuration Management:** https://csrc.nist.gov/pubs/sp/800/128/upd1/final
- **OWASP, Authorization Cheat Sheet:** https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
