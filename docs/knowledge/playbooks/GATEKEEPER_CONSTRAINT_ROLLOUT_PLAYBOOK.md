# Gatekeeper ConstraintTemplate + Constraint Rollout Playbook

## Purpose

Define a controlled procedure to introduce a new Open Policy Agent Gatekeeper `ConstraintTemplate` CRD and matching `Constraint` resources, progressing from dry-run through `warn` to `deny` enforcement without breaking live workloads.

## Audience

Platform engineers operating the Gatekeeper controller, security engineers owning the Rego templates, and SREs responsible for cluster workload reliability.

## Pre-conditions

- Gatekeeper version is pinned per `docs/knowledge/reference/GATEKEEPER_VERSION_GOVERNANCE.md` and the controller is healthy.
- The `ConstraintTemplate` Rego is unit-tested with `opa test` against representative fixtures.
- The matching `Constraint` YAML is stored in the GitOps repo and references the template via `kind` and `apiVersion` (typically `constraints.gatekeeper.sh/v1beta1`).
- A baseline inventory of in-cluster audit violations exists so regressions are detectable.
- Change ticket approved and a maintenance window scheduled for the `enforcementAction: deny` flip.

## Procedure

### Step 1 - Install or refresh the ConstraintTemplate

1. Apply the `ConstraintTemplate` CRD first; verify with `kubectl get crd constrainttemplates.templates.gatekeeper.sh`.
2. Confirm the template reports `Status: Created` and the generated CRD exists.

### Step 2 - Stage the Constraint in dry-run

3. Apply the `Constraint` with `enforcementAction: dryrun`.
4. Watch the audit log: `kubectl get events --field-selector reason=AuditViolation -A`.
5. Compare current violations against the pre-rollout baseline; record deltas per namespace and `kind`.
6. Do not advance until the violation trend is understood and triaged.

### Step 3 - Move to warn mode

7. Edit the `Constraint` to `enforcementAction: warn` (Gatekeeper 3.13+).
8. Re-run a synthetic workload that previously violated; confirm a warning is returned but the object is admitted.

### Step 4 - Promote to deny

9. Begin with `match.scope: Namespaced` and an `excludedNamespaces` allow-list for known exceptions.
10. Flip to `enforcementAction: deny` only after the warn window shows no critical regressions.
11. Capture admission latency from Gatekeeper metrics before and after the flip; abort if p99 regresses beyond the agreed SLO.

### Step 5 - Verify and expand

12. Run a representative workload suite; deny on bad input, admit on good input.
13. Remove the namespace allow-list only after telemetry is green.

## Rollback

- Revert the `Constraint` to `enforcementAction: warn` via GitOps; reconciliation restores permissive behavior.
- If a template regression is suspected, recreate the prior `ConstraintTemplate` to restore the previous CRD schema.
- For emergencies, label the `Constraint` with `gatekeeper.sh/disabled: "true"` or delete it while leaving the template installed.
- Re-baseline audit violations after rollback and notify workload owners of the temporary relaxation window.

## References

- `docs/knowledge/reference/GATEKEEPER_VERSION_GOVERNANCE.md`
- `docs/knowledge/operations/CNCF_KYVERNO_POLICY_AS_CODE_GOVERNANCE.md`
- https://open-policy-agent.github.io/gatekeeper/website/docs/constrainttemplates/
- https://open-policy-agent.github.io/gatekeeper/website/docs/enforcementaction/
- https://open-policy-agent.github.io/gatekeeper/website/docs/audit/
