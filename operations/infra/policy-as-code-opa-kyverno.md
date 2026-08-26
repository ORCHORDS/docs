# policy-as-code-opa-kyverno

Policy-as-code is the 2026 way to enforce "you can't deploy an untagged
resource / a public S3 bucket / a privileged pod" before it reaches prod.
Two tools dominate Kubernetes: **OPA Gatekeeper** (general-purpose Rego) and
**Kyverno** (YAML-native, K8s-focused). This article covers the patterns and
friction teams hit rolling out either.

## Symptom

- A developer ships a Deployment with `image: latest` and prod rolls every
  time someone happens to push to the registry.
- A pod mounts `hostPath: /` and gets cluster-admin via a node escape.
- An S3 bucket with `public-read-write` slips through code review.
- An engineer opens a PR that would create a security group allowing
  `0.0.0.0/0` on port 22 — Terraform plan is green, the review is the only
  thing stopping it.
- Half the team's pods land in a namespace with no ResourceRequests and the
  cluster gets starved.

## Why Policy-as-Code

- Code review catches what humans remember to look for. Policy-as-code catches
  everything, every time, including at 2am Friday deploys.
- Shifts left: fails the bad config in CI before it ever reaches the cluster
  or cloud, instead of firing a post-deploy security finding.
- Auditable: the policy is in Git, changes are reviewable, evidence is
  automatic for SOC2/ISO27001.

## Fix: Kyverno — block `latest` image tags (admission control)

```yaml
# policies/disallow-latest-tag.yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: disallow-latest-tag
spec:
  validationFailureAction: Enforce     # Enforce = block; Audit = warn only
  background: true                     # also scan existing resources
  rules:
    - name: require-image-tag
      match:
        any:
          - resources:
              kinds: ["Pod"]
      validate:
        message: "Images must not use the ':latest' tag. Pin a digest or version."
        pattern:
          spec:
            containers:
              - image: "!*:latest"     # Kyverno pattern syntax
```

Apply with `kubectl apply -f`. From now on, any pod create/update with a
`:latest` image is rejected at the API server. Start in `Audit` mode for 2
weeks to see what would break, then flip to `Enforce`.

## Fix: Kyverno — require resource requests and labels

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: require-requests-and-owner
spec:
  validationFailureAction: Enforce
  rules:
    - name: require-requests
      match:
        any:
          - resources:
              kinds: ["Pod"]
      validate:
        message: "All containers must define cpu/memory requests and limits."
        pattern:
          spec:
            containers:
              - resources:
                  requests:
                    memory: "?*"
                    cpu: "?*"
                  limits:
                    memory: "?*"
    - name: require-owner-label
      match:
        any:
          - resources:
              kinds: ["Pod", "Deployment", "Service"]
      validate:
        message: "Resources must have an 'owner' label for cost attribution."
        pattern:
          metadata:
            labels:
              owner: "?*"
```

## Fix: OPA Gatekeeper — same disallow-latest rule in Rego

```rego
# policies/disallow_latest_tag.rego
package k8sdisallowedlatesttag

violation[{"msg": msg}] {
  container := input.review.object.spec.containers[_]
  endswith(container.image, ":latest")
  msg := sprintf("image '%v' uses ':latest' — pin a version", [container.image])
}

violation[{"msg": msg}] {
  container := input.review.object.spec.containers[_]
  not contains(container.image, ":")
  msg := sprintf("image '%v' has no tag — default registry behavior is unsafe", [container.image])
}
```

```yaml
# ConstraintTemplate + Constraint to wire it into Gatekeeper
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8sdisallowedlatesttag
spec:
  crd:
    spec:
      names:
        kind: K8sDisallowedLatestTag
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package k8sdisallowedlatesttag
        violation[{"msg": msg}] {
          container := input.review.object.spec.containers[_]
          endswith(container.image, ":latest")
          msg := sprintf("image uses ':latest'", [])
---
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sDisallowedLatestTag
metadata:
  name: no-latest-tag
spec:
  enforcementAction: deny     # deny | dryrun | warn
  match:
    kinds:
      - apiGroups: [""]
        kinds: ["Pod"]
```

## Fix: Terraform policy with OPA (Conftest / OPA)

```hcl
# main.tf
resource "aws_s3_bucket_acl" "b" {
  bucket = aws_s3_bucket.b.id
  acl    = "public-read"    # policy should reject this
}
```

```rego
# policies/s3.rego
package terraform

deny[msg] {
  resource := input.planned_values.root_module.resources[_]
  resource.type == "aws_s3_bucket_acl"
  resource.values.acl == "public-read"
  msg := sprintf("S3 bucket %v must not be public-read", [resource.name])
}

deny[msg] {
  resource := input.planned_values.root_module.resources[_]
  resource.type == "aws_security_group_rule"
  resource.values.cidr_blocks[_] == "0.0.0.0/0"
  resource.values.from_port == 22
  msg := "security group rule opens SSH to the world"
}
```

```bash
# in CI: run after `terraform plan`, fail the build on deny
terraform plan -out=plan.bin
terraform show -json plan.bin > plan.json
opa eval -d policies/ -i plan.json 'data.terraform.deny'
# exit non-zero if any deny[] entries returned
```

## Fix: CI pre-commit with Conftest (shift-left before the PR)

```yaml
# .github/workflows/policy.yml
- name: Conftest
  run: |
    curl -sL https://github.com/open-policy-agent/conftest/releases/latest/download/conftest_Linux_x86_64.tar.gz | tar xz
    # validate every YAML in the repo against policies/
    find . -name '*.yaml' -path '*/manifests/*' -exec ./conftest test --policy policies/ {} +
```

Developers see policy failures locally before opening the PR, not after.

## Choosing Kyverno vs OPA Gatekeeper

- **Kyverno** — pick if your team lives in YAML/Kubernetes-native thinking
  and wants lower friction. Pattern matching reads like the resources it
  validates. Good default for K8s-only policies.
- **OPA Gatekeeper** — pick if you need one engine across K8s, Terraform, CI,
  API authorization, and service mesh. Rego is more expressive but steeper.
  Good when policies span multiple domains.

Both integrate with admission controllers and CI. Many orgs run Kyverno for
K8s and OPA/Conftest for Terraform — they're complementary, not exclusive.

## Gotchas

- **Always start in `Audit` / `dryrun` mode.** `Enforce` from day one will
  break something you didn't anticipate. Run 2 weeks of audit-mode telemetry,
  review violations, then flip per-policy to enforce.
- **`background: true` policies scan existing resources.** A newly-enforced
  policy can mark existing workloads non-compliant and block updates to them
  even though the original create was allowed. Decide whether to grandfather
  or remediate.
- **Rego is Turing-complete and unreadable when abused.** Complex policies
  become unmaintainable. Cap policy complexity; if a rule can't be explained
  in one English sentence, split it.
- **Policy ordering matters in Kyverno when mutating.** A `mutate` rule that
  injects labels must run before a `validate` rule that requires them. Use
  `spec.rules[].preconditions` and test the order with `kyverno apply`.
- **Excluded namespaces need to be explicit.** `kube-system`, `gatekeeper-system`,
  `kyverno-system`, and any CI/CD runner namespace usually need to be exempt
  or they break cluster plumbing. Add them to `match.exclude`.
- **ConstraintTemplates are cluster-scoped.** A bad Rego template can break
  the entire admission chain. Test in a non-prod cluster first; gate
  ConstraintTemplate changes via PR review.
- **Policy drift between clusters.** If dev allows `latest` but prod blocks
  it, devs build on dev then prod rejects. Keep policies in a single Git
  repo and sync to all clusters via GitOps so dev catches what prod will catch.
- **Reporting matters as much as enforcement.** Gatekeeper audit results and
  Kyverno policy reports are how you prove compliance to auditors. Wire them
  to a dashboard; don't just rely on "the deploy failed."
- **Performance: Gatekeeper can add 100-500ms to every API write** with many
  constraints. Keep constraint count reasonable; test cluster control-plane
  latency under load.
- **`warn` enforcementAction in Gatekeeper is silent in `kubectl`.** The user
  doesn't see the warning unless they look at API response details. Don't
  rely on `warn` as a feedback channel — use it as a logging signal, not a
  UX. For user-visible feedback, block (`deny`) or use Kyverno's `warn` mode
  which surfaces in `kubectl` output.
