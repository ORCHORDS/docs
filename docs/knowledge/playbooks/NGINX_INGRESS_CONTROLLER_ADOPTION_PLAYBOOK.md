# NGINX Ingress Controller Adoption Playbook

## Purpose

Adopt the NGINX Ingress Controller (NIC) for cluster ingress with a stable upgrade path, a clear TLS posture, and an opt-in ModSecurity/WAF toggle so application owners can expose HTTP/S services without re-implementing TLS, rate-limiting, or WAF logic per workload.

## Audience

Platform engineers, security engineers, and application owners who expose HTTP/S workloads through a Kubernetes cluster.

## Pre-conditions

- `docs/knowledge/reference/NGINX_INGRESS_CONTROLLER_VERSION_GOVERNANCE.md` reviewed and the target NIC version pinned.
- cert-manager deployed with an issuer (internal CA or ACME) per `CERT_MANAGER_VERSION_GOVERNANCE.md`.
- HTTPRoute (Gateway API) or Ingress CRDs available in the cluster and the ingress class name agreed cluster-wide (for example `nginx`).
- Helm chart version pinned and verified compatible with the Kubernetes minor version.
- A namespace for the controller, a metrics sink, and a notification target for upgrade outcomes are pre-provisioned.

## Procedure

### Step 1 — Install the controller via Helm

1. Add the ingress-nginx Helm repository and pin the chart version from `NGINX_INGRESS_CONTROLLER_VERSION_GOVERNANCE.md`.
2. Render values with `controller.replicaCount=2`, `controller.minAvailable=1` in the PodDisruptionBudget, `controller.publishService.enabled=true`, and `controller.metrics.enabled=true`.
3. Install with `helm install ingress-nginx ingress-nginx/ingress-nginx -n ingress-nginx -f values.yaml`.
4. Confirm two controller pods are Ready and that the published Service has an external IP or LoadBalancer hostname.

### Step 2 — Apply RBAC and ClusterRole

5. Confirm the chart-rendered `ServiceAccount`, `ClusterRole`, and `ClusterRoleBinding` objects are present; do not replace with narrower RBAC until the first rollout succeeds.
6. Restrict the `ClusterRole` to the namespaces that own Ingress/HTTPRoute objects once the migration completes.
7. Validate with `kubectl auth can-i list ingresses --as=system:serviceaccount:ingress-nginx:ingress-nginx -n <ns>`.

### Step 3 — Dry-run with admission webhooks disabled

8. Set `controller.admissionWebhooks.enabled=false` for the first install so existing Ingress objects are not mutated.
9. Run `helm diff upgrade ingress-nginx ingress-nginx/ingress-nginx -n ingress-nginx` against the live release to inspect what would change.
10. Re-enable admission webhooks only after every workload owner has confirmed Ingress annotations render correctly.

### Step 4 — Configure default backend TLS via cert-manager

11. Annotate the controller's default backend Service with `cert-manager.io/cluster-issuer: <issuer>` and request a wildcard Certificate for the cluster domain.
12. Reference the resulting Secret in the controller values (`controller.defaultTLS.secret.namespace` and `.name`) so the TLS default backend terminates cleanly.
13. Verify with `openssl s_client -connect <lb-host>:443 -servername <host>` that the chain and SANs match the wildcard.

### Step 5 — Install ModSecurity / OWASP CRS as opt-in

14. Set `controller.config.enable-modsecurity=true` and add `modsecurity-snippet` annotations on a per-Ingress basis so the OWASP CRS is opt-in per workload.
15. Switch `modsecurity-transaction-id` and SecRuleEngine between `DetectionOnly` and `On` per environment; keep staging on `On` and production on `DetectionOnly` until baselined.
16. Capture false-positive rules in a `modsecurity-snippet` allow-list and document them in the runbook before tightening.

### Step 6 — Run the chart-upgrade runbook for past minor versions

17. Read past release notes for each minor bump and confirm CRD changes, deprecated annotations, and `controller.service.type` defaults before running `helm upgrade`.
18. Upgrade one minor version at a time and re-run `helm diff upgrade` between revisions so the change set is reviewable.
19. Keep at least three prior revisions in `helm history` so `helm rollback` has a known-good target.

## Rollback

- Inspect revisions with `helm history ingress-nginx -n ingress-nginx` and roll back with `helm rollback ingress-nginx <revision>`; verify the previous controller image and config are restored.
- If a CRD upgrade forced breaking changes, halt the controllers (`kubectl scale deploy ingress-nginx-controller --replicas=0`) before reverting the CRDs, then roll back the Helm release.
- If a bad TLS secret leaked, revoke through cert-manager (`cmctl revoke -n <ns> <secret-name>`) and reissue the certificate from the issuer before re-attaching the secret to the controller.

## References

- `docs/knowledge/reference/NGINX_INGRESS_CONTROLLER_VERSION_GOVERNANCE.md`
- `docs/knowledge/reference/CERT_MANAGER_VERSION_GOVERNANCE.md`
- ingress-nginx documentation: `https://kubernetes.github.io/ingress-nginx/`
- ModSecurity integration: `https://kubernetes.github.io/ingress-nginx/user-guide/third-party-addons/modsecurity/`
