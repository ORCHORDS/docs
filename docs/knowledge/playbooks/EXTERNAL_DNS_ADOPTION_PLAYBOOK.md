# external-dns Adoption Playbook

## Purpose

Sync Kubernetes Services and Ingresses (and Gateway HTTPRoutes, where supported) to external DNS providers automatically, with controlled ownership, deterministic naming, and a sandbox-first rollout so DNS record churn cannot surprise production zones.

## Audience

Platform engineers, SREs, and application owners who publish services through Kubernetes and need authoritative DNS to follow cluster state without manual zone edits.

## Pre-conditions

- `docs/knowledge/reference/EXTERNAL_DNS_VERSION_GOVERNANCE.md` reviewed and the target version pinned.
- DNS provider chosen and account/zone verified (Route53, CloudDNS, Azure DNS, Cloudflare, or RFC2136).
- IAM or IRSA scope set to the narrowest set of zones the controller needs (no wildcard `*` on `route53:*` or equivalent).
- Registry-owner TXT pattern agreed (for example `external-dns-owner=<deploy-id>`) so multiple external-dns instances can share a zone without overwriting each other.
- Domain filter set (allow-list of zones the controller will manage) and a sandbox subdomain reserved for the first rollout.
- Metrics sink and alert target pre-provisioned; PodDisruptionBudget values decided for the target environment.

## Procedure

### Step 1 — Install external-dns via Helm with provider secret

1. Add the external-dns Helm repository and pin the chart version from `EXTERNAL_DNS_VERSION_GOVERNANCE.md`.
2. Render values with the provider set (`provider: aws/cloudflare/google/azure/rfc2136`), the registry-owner TXT pattern, the domain filter, and the policy defaulted to `upsert-only`.
3. Install with `helm install external-dns external-dns/external-dns -n external-dns -f values.yaml` and confirm the pod is Ready.
4. Confirm the provider credentials resolve by tailing the controller logs for a successful zone-list response on first sync.

### Step 2 — Configure registry ownership TXT

5. Set `txt-owner-id` to the deploy instance ID and `txt-prefix` to a value unique per environment (for example `prod-`, `staging-`).
6. Set `registry=txt` so existing CNAME/A records created by other tooling are not silently overwritten.
7. Verify with `dig TXT _external-dns.<sandbox-zone>` that the registry TXT is present and matches the configured owner before any Service/Ingress is annotated.

### Step 3 — Annotate Services and Ingresses

8. Add `external-dns.alpha.kubernetes.io/hostname: <fqdn>` (or the Gateway-API equivalent) to a sandbox Service or Ingress first; avoid production annotations until the sandbox flow is observed.
9. Add `external-dns.alpha.kubernetes.io/ttl: "60"` for short-lived test records, then raise to your production TTL once stable.
10. Re-confirm the controller picks the new annotation up by watching its logs and the resulting provider-side record after the next reconcile interval.

### Step 4 — Set policy and sandbox subdomain

11. Run the first end-to-end test with `--policy=upsert-only` against the sandbox subdomain so the controller cannot delete pre-existing records.
12. After the sandbox record materializes and resolves, review the record's content (CNAME target, A record value, TTL) against the Service/Ingress definition.
13. Promote to `--policy=sync` only after the sandbox subdomain has been reviewed by the platform and security owners.

### Step 5 — Enable metrics, PDB, and notifications

15. Set `metrics.enabled=true` and expose the `/metrics` endpoint to the cluster Prometheus so reconcile failures and per-record latency are observable.
16. Define a `PodDisruptionBudget` with `minAvailable=1` and add topology spread constraints so the controller survives node drains.
17. Configure a notification target (Slack or webhook) for `WARN`/`ERROR` controller logs so DNS drift triggers an alert on the same channel as cluster alerts.

### Step 6 — First production rollout under freeze-and-review

18. Annotate the first wave of production Services and Ingresses with `--policy=upsert-only` and a hard `txt-owner-id` per deploy instance.
19. Freeze the rollout, run `kubectl logs`, and review every record the controller created or modified in the provider console before granting the next wave of annotations.
20. Re-enable `--policy=sync` only after the freeze-and-review pass and document the cadence for future waves.

## Rollback

- Delete the external-dns TXT ownership record (`dig -t TXT _external-dns.<zone>` to find, then remove through the provider's own API in dry-run) so the controller stops claiming ownership.
- Pause sync by setting `--policy=upsert-only` while draining, which prevents deletes but allows owner-aligned updates to converge.
- For mis-recorded entries, prefer the provider's audit log and remove records through the provider's own API in dry-run before re-enabling Image Updater-style auto-publish flows.
- Uninstall the Helm release last; ownership TXT removal ensures no other controller re-creates records after uninstall.

## References

- `docs/knowledge/reference/EXTERNAL_DNS_VERSION_GOVERNANCE.md`
- external-dns docs: `https://github.com/kubernetes-sigs/external-dns`
- AWS IRSA notes: `https://github.com/kubernetes-sigs/external-dns/blob/master/docs/tutorials/aws.md`
- Cloudflare provider notes: `https://github.com/kubernetes-sigs/external-dns/blob/master/docs/tutorials/cloudflare.md`
