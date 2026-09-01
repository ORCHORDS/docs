# Bicep What-If Deployment Gates

**Issue:** Azure Bicep templates describe desired-state infrastructure declaratively, but the gap between the template and a real `az deployment` is where most accidental damage happens. Operators who deploy without first running `bicep build` and `az deployment what-if` cannot tell whether their next apply will succeed or quietly destroy a resource that another team depends on. The deployment-gate workflow uses what-if as a deterministic policy decision point, not as a passive preview.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What What-If Actually Does

`az deployment what-if` accepts the same template parameters and template-spec inputs as `az deployment create` and computes the diff between the template's desired state and Azure's current state. The output enumerates every resource that would be created, modified, deleted, or ignored, with a per-resource `changeType` field. The engine reads Azure Resource Manager state via the same control-plane APIs that a real deployment would use, so what-if output is an accurate preview of what the next deployment will do.

What-if is non-mutating. The control-plane state used for the comparison is a read-only snapshot of the resources' actual state, not their last-deployed state. This is what makes what-if useful for drift detection in addition to change preview: a resource whose actual state differs from the last-deployed state will appear in the what-if output as a change, even if the template has not changed since the last successful deployment. The operator can therefore use what-if as both a change preview and a drift detector.

## Constructing The Gate

A deployment gate is a CI step that runs what-if and rejects the deploy if the output includes disallowed change types. The simplest gate rejects any change of type `Delete` or `Modify` for a tagged subset of resources, requiring a separate review workflow for those resources. A more sophisticated gate accepts `Create` and `Ignore` changes but rejects `Modify` for resources tagged as immutable; the engine supports this through the `--exclude-change-types` parameter and custom rule evaluation in CI.

The gate must run against the same scope and parameters that the real deployment will use. Running what-if against a different subscription or resource group gives a meaningless result. Wire the gate into the same pipeline as the real deployment so that the parameters, secrets, and scope are sourced from the same configuration; a parameter mismatch between what-if and deploy is the most common cause of a green gate followed by a destructive apply.

## Resource Tags As Policy Surface

Bicep supports `tags` on most resource types, and operators can encode policy by reading tags from the what-if output and applying policy rules in CI. A common pattern is to tag resources with `immutable: true` and have the gate reject any change to those resources. Another pattern is to tag with `data-classification: confidential` and reject any change that would alter network exposure or access controls. The tag is the policy surface that the gate enforces; without it, the gate must guess intent from the resource type.

The what-if output includes the new tag values the deployment would apply, so the gate can detect tag changes that affect policy. A resource that was `immutable: true` and is being changed to `immutable: false` and then modified is a two-step change that the gate should reject. The fix is to require that policy-affecting tags be changed through a separate review pipeline that updates both the resource and the gate's rule set.

## Complete vs Incremental Mode

`az deployment what-if` runs in two modes: complete, which compares the template's full desired state to Azure's full state, and incremental, which only checks resources the template declares. Complete mode is the safer default because it detects resources that exist in Azure but are not in the template; an out-of-band resource will not be silently ignored. Incremental mode is faster and produces less output for large templates, but it should only be used when the template is the authoritative inventory.

The mode is set per command via the `--mode` parameter; CI should default to complete and only switch to incremental for templates that are known to be authoritative. Switching modes mid-pipeline is a flag-smell that warrants review; the inconsistency usually indicates that the template and the real Azure state have drifted in ways the team has not yet investigated.

## Failure Modes

The most damaging failure is a what-if that passes because the gate only inspects the change types but ignores the change magnitudes. A `Modify` change that resizes a database from 1 GB to 1 TB is a small text change in the what-if output but a catastrophic billing event. The gate must evaluate the magnitude of changes, not just the type, for high-cost resources. Use Azure Cost Management APIs or a cost-estimation tool to predict the cost delta and reject applies that exceed a configured threshold.

A second failure is what-if running against a different principal than the real deployment. The what-if output reflects what the gate's identity can see, but the real deployment runs under a different identity with different RBAC. A what-if that says "no changes" because the gate identity lacks read permission for a resource is dangerously misleading. Run what-if under the deployment identity, or under an identity with identical RBAC; the gate and the deployer must operate with the same visibility.

A third failure is a gate that requires human approval for every `Modify` change. The approval workflow quickly becomes a bottleneck and operators learn to work around it by splitting changes into multiple deployments to avoid triggering the gate. Configure the gate with clear, narrow rules and an explicit escalation path so that operators do not need to bypass the gate to ship legitimate work.

## Canonical sources

1. https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deploy-what-if
2. https://learn.microsoft.com/en-us/azure/azure-resource-manager/templates/deploy-what-if