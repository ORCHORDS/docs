# Terraform action-trigger plan and approval boundary

**Issue:** Provider actions can restart systems or invoke external automation without changing Terraform resource state, so a familiar zero-resource-change plan can still contain irreversible operational work.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Require Terraform 1.14 or later, pin a provider that implements the action, and treat every action as an external side effect with its own authorization and rollback plan.
- Review the plan's action count and addresses in addition to add/change/destroy counts. A plan with `0` resource changes is not necessarily inert.
- For lifecycle `action_trigger`, select only the required before/after create or update events, use a narrow condition, and review the ordered action list.
- Keep actions idempotent or protected by a remote operation key. Do not assume Terraform state records enough information to undo or deduplicate them.
- Separate ad-hoc CLI `-invoke` authority from ordinary plan authority and require explicit production approval.

## Verification

Test every configured event, false and unknown conditions, drift-only updates, repeated apply, partial failure between ordered actions, provider timeout, and retry. Assert the plan names the invocation and verify the external system after apply because actions do not write their result into resource state.

## Gotchas

- Provider availability and semantics are action-type specific.
- Before-actions can block a resource change; after-actions can fail after the resource already changed.
- External work may continue after the Terraform process loses its response.

## Official source

- [Terraform: invoke an action](https://developer.hashicorp.com/terraform/language/invoke-actions)
- [Terraform lifecycle action_trigger](https://developer.hashicorp.com/terraform/language/meta-arguments/lifecycle#action_trigger)
