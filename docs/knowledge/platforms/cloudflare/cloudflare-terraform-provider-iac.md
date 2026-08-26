# cloudflare-terraform-provider-iac

**Issue:** Zones, DNS records, WAF rules, Workers scripts, R2 buckets, D1 databases, and Access policies are all API-configurable, which means every dashboard edit is an untracked production change that the next Terraform apply will silently revert — or that drifts forever. The `cloudflare/cloudflare` Terraform provider (v5.x) can own all of it, but adopting it badly (one giant state, partial imports, apply-by-hand from laptops) creates more blast radius than it removes. This article covers provider structure, the Wrangler-vs-Terraform split for Workers, import-first adoption, and the CI discipline that keeps state honest. It targets platform decisions, not resource-by-resource syntax.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Structure and state boundaries

1. **Directory per account/zone/product, not one root module.** Cloudflare's own best-practices doc recommends isolating changes by account, zone, and product — separate state per boundary. A `global/` (account-level: Workers, R2, Access), `zones/<zone>/` (DNS, SSL, WAF), and product-specific subdirs layout means a bad apply on one zone cannot take out account-level resources.
2. **Remote state with locking, always.** S3/R2-compatible backend (or Terraform Cloud) with state locking; local state plus multiple engineers is how two applies corrupt a zone. One state per directory from day one — splitting state later requires `state mv` surgery.
3. **Scoping credentials.** Provider auth via `CLOUDFLARE_API_TOKEN` env var in CI, using a token scoped to the exact account/zone permissions the root modules manage. This doubles as guardrails: Terraform literally cannot touch resources outside its token scope.
4. **Pin the provider version.** `cloudflare/cloudflare` moved to v5.x with breaking resource renames/argument changes; pin the major in `required_providers` and upgrade deliberately, reading the upgrade guide per major. Floating `~> 5` latest-minor is usually fine; floating majors are not.

## What Terraform should own vs Wrangler

1. **Config-plane resources belong to Terraform.** DNS records, zone settings overrides, WAF custom rules and rulesets, Access applications/policies, R2 buckets (with lifecycle rules), D1 databases, KV namespaces, Queues, Workers routes and custom domains, logpush jobs — anything that is "configuration that exists" rather than "code that runs."
2. **Worker code deployment is a judgment call.** `cloudflare_workers_script` can ship the script itself — including full-stack Workers with static assets since provider v5.11.0 (Oct 2025). The pragmatic split most teams land on: Wrangler handles app code and bindings in the app repo's CI, Terraform owns surrounding config (routes, domains, DNS). One Worker, two systems is fine — but never manage the same attribute in both.
3. **Secrets stay out of state.** Never put Worker secret values in Terraform variables — they land in state plaintext. Use `wrangler secret put`/Secrets Store bindings for values, and at most Terraform-managed placeholder rotation metadata.
4. **Import before managing anything existing.** Zones configured by hand must be imported (`terraform import`, or Terraform 1.5+ `import` blocks) before apply, otherwise the first apply tries to recreate records and rules that already exist. Generate the import plan from `terraform plan` output, not memory.

## Import-first adoption path

1. **Inventory before writing HCL.** List what exists per zone (DNS, page rules, firewall, SSL mode) via dashboard or API; decide explicitly what Terraform will own now, later, or never. "Later" and "never" items must be excluded by resource-scope, not just omitted and forgotten.
2. **Start with DNS for one zone.** Import `cloudflare_record` resources, get green plans, then expand to zone settings and WAF. Attempting the whole account in one PR is how adoption projects die mid-migration with half-imported state.
3. **Import dashboards edits as they happen.** The standing rule after adoption: no manual changes, full stop. If an emergency requires a hotfix in the dashboard, the owner imports that change into Terraform the same day — otherwise the next apply reverts the emergency fix at the worst possible moment.
4. **Expect churn arguments on zone settings.** `cloudflare_zone_settings_override` owns many settings at once and shows noisy diffs when the dashboard nudges defaults; scope the settings block to the ones you actually manage to keep plans readable.

## CI/CD and drift discipline

1. **Plan on PR, apply on merge.** GitHub Actions (or equivalent) runs `terraform fmt -check`, `validate`, and `plan` on pull requests with the plan posted for review; `apply` only from the default branch. Local applies against remote state are disabled by policy, not just convention.
2. **Scheduled drift detection.** A nightly `terraform plan -detailed-exitcode` job that comments or alerts on non-empty diffs catches dashboard drift and rogue applies early. Drift alerts that everyone ignores are worse than none — route them to the owning team.
3. **State encryption and access review.** State contains sensitive values (tokens referenced, rule expressions); restrict backend access like production secrets, and rotate the CI API token on a schedule using least-privilege scopes.
4. **Modularize repeated shapes.** Zones with identical posture (DNS + WAF + Access + logpush) become a module instantiated per zone (community modules like CloudPosse's zone module exist as references); per-zone variation lives in a small tfvars file, not copy-pasted HCL.
5. **Learn from Cloudflare's own scale story.** The "Terraforming Cloudflare at Cloudflare" blog documents how they isolate state by boundary and manage config-as-code across thousands of zones — the same account/zone/product split, validated at maximum scale.

## References

1. **Cloudflare Terraform best practices.** developers.cloudflare.com/terraform/advanced-topics/best-practices/ — directory structure and isolation guidance.
2. **cloudflare_workers_script resource.** registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/workers_script — including static assets support.
3. **Terraforming Cloudflare at Cloudflare.** blog.cloudflare.com/terraforming-cloudflare-at-cloudflare/.
4. **Changelog: Workers with assets via Terraform (v5.11.0).** developers.cloudflare.com/changelog/post/2025-10-09-assets-terraform/.
