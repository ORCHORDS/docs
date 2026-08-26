# SOPS + age: GitOps-Native Secrets Management

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Kubernetes manifests and Helm values containing secrets cannot be committed to the GitOps repo,
so engineers either hard-code them in CI environment variables or maintain a separate out-of-band
runbook — both break the GitOps single-source-of-truth principle.

## Context
Mozilla SOPS (Secrets OPerationS) encrypts specific YAML/JSON values in-place while leaving
keys and structure readable, so diffs remain meaningful in pull requests.
`age` (pronounced "agey") is a modern, auditable file encryption tool that replaces GPG;
its public/private keypair is small, easy to rotate, and has no keyring daemon.
Together they enable encrypted secrets committed to Git, decrypted only in the cluster
by Flux or ArgoCD using a key stored in a Kubernetes Secret or via AWS KMS / cloud KMS.

## Generating age Keys and Configuring SOPS

```bash
# Install age
brew install age          # macOS
apt install age           # Debian/Ubuntu

# Generate a key pair (one per environment or per human)
age-keygen -o ~/.config/sops/age/keys.txt
# Output: public key = age1abcdef...

# Store public key in .sops.yaml at repo root — this file is NOT secret
```

```yaml
# .sops.yaml (committed to repo root)
creation_rules:
  # Production secrets: require two age recipients (GitOps key + break-glass key)
  - path_regex: ^k8s/production/.*\.enc\.yaml$
    age: >-
      age1prod000aaabbbccc111222333444555666777888999aaabbbccc111222333,
      age1breakglass000xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    encrypted_regex: "^(data|stringData)$"

  # Staging: single GitOps key is sufficient
  - path_regex: ^k8s/staging/.*\.enc\.yaml$
    age: age1staging111aaabbbccc444555666777888999aaabbbccc444555666777888

  # Helm values files
  - path_regex: ^helm/.*\.enc\.yaml$
    age: >-
      age1prod000aaabbbccc111222333444555666777888999aaabbbccc111222333
    encrypted_regex: "^(password|apiKey|token|secret|connectionString)$"
```

## Encrypting and Editing Secrets

SOPS in-place encryption: only values matching `encrypted_regex` are ciphered.

```bash
# Create a new encrypted secret
cat > /tmp/db-credentials.yaml <<'EOF'
apiVersion: v1
kind: Secret
metadata:
  name: db-credentials
  namespace: production
type: Opaque
stringData:
  password: "<redacted-secret>"
  connectionString: "postgresql://user:super-secret-db-password-123@db.internal:5432/orchords"
EOF

# Encrypt in-place (reads .sops.yaml for recipients)
SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt \
  sops --encrypt /tmp/db-credentials.yaml > k8s/production/db-credentials.enc.yaml

# Edit an existing encrypted file (decrypts to $EDITOR, re-encrypts on save)
SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt \
  sops k8s/production/db-credentials.enc.yaml
```

Encrypted file looks like (safe to commit):

```yaml
# k8s/production/db-credentials.enc.yaml
apiVersion: v1
kind: Secret
metadata:
    name: db-credentials
    namespace: production
type: Opaque
stringData:
    password: ENC[AES256_GCM,data:Xyz123...==,tag:abc==,type:str]
    connectionString: ENC[AES256_GCM,data:Def456...==,tag:def==,type:str]
sops:
    age:
        - recipient: age1prod000...
          enc: |
              -----BEGIN AGE ENCRYPTED FILE-----
              ...
              -----END AGE ENCRYPTED FILE-----
    lastmodified: "2026-08-23T10:00:00Z"
    version: 3.8.1
```

## Flux Integration (SOPS Decryption in Cluster)

Flux's `kustomize-controller` natively supports SOPS; it decrypts manifests at apply time
using the age private key stored as a Kubernetes Secret in the `flux-system` namespace.

```bash
# Store the age private key in the cluster (once, during bootstrap)
kubectl create secret generic sops-age \
  --namespace=flux-system \
  --from-file=age.agekey=$HOME/.config/sops/age/keys.txt
```

```yaml
# flux/kustomization-production.yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: production-secrets
  namespace: flux-system
spec:
  interval: 10m
  path: ./k8s/production
  prune: true
  sourceRef:
    kind: GitRepository
    name: orchords-fleet
  decryption:
    provider: sops
    secretRef:
      name: sops-age
```

Flux will automatically decrypt `.enc.yaml` files when it applies the kustomization.

## CI/CD: Decrypting Secrets in GitHub Actions

For CI pipelines that need to inject secrets into build steps without committing them plaintext:

```yaml
# .github/workflows/deploy-staging.yml
name: Deploy Staging

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install sops and age
        run: |
          wget -qO /usr/local/bin/sops \
            https://github.com/getsops/sops/releases/download/v3.9.1/sops-v3.9.1.linux.amd64
          chmod +x /usr/local/bin/sops
          sudo apt-get install -y age

      - name: Decrypt staging secrets
        env:
          SOPS_AGE_KEY: ${{ secrets.SOPS_AGE_PRIVATE_KEY_STAGING }}
        run: |
          # Decrypt to stdout, pipe to kubectl apply
          sops --decrypt k8s/staging/db-credentials.enc.yaml | kubectl apply -f -

      - name: Extract a single value for build env
        env:
          SOPS_AGE_KEY: ${{ secrets.SOPS_AGE_PRIVATE_KEY_STAGING }}
        run: |
          API_KEY=$(sops --decrypt --extract '["stringData"]["apiKey"]' \
            k8s/staging/api-credentials.enc.yaml)
          echo "::add-mask::$API_KEY"
          echo "API_KEY=$API_KEY" >> $GITHUB_ENV
```

## Key Rotation Procedure

```bash
# 1. Generate new age key
age-keygen -o /tmp/new-keys.txt
NEW_PUBLIC_KEY=$(head -1 /tmp/new-keys.txt | grep "public key" | awk '{print $4}')

# 2. Update .sops.yaml to add new key as a recipient alongside the old one
# (both keys can decrypt during the transition window)

# 3. Re-encrypt all affected files with both keys
find k8s/ -name "*.enc.yaml" | while read f; do
  SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt sops updatekeys -y "$f"
done

# 4. Rotate the in-cluster secret
kubectl create secret generic sops-age \
  --namespace=flux-system \
  --from-file=age.agekey=/tmp/new-keys.txt \
  --dry-run=client -o yaml | kubectl apply -f -

# 5. Remove the old recipient from .sops.yaml and re-encrypt to evict old key
```

## Anti-patterns
- Committing the age private key to the repo — only public keys belong in `.sops.yaml`
- Using a single global age key for all environments — rotate compromise blast radius equals all secrets
- Encrypting only secret values but leaving secret names unencrypted when names themselves are sensitive — use `encrypted_regex: "^(data|stringData|metadata)$"` for full encryption
- Storing SOPS-encrypted files with `.yaml` extension without `.enc.` in the filename — makes it unclear at a glance which files need a key to edit
- Using GPG instead of age — GPG keyring management is complex and `age` is a drop-in replacement

## Gotchas
- `sops updatekeys` requires the OLD private key to be present; keep old keys accessible until all files are re-encrypted
- Flux's `kustomize-controller` requires the age key file to be named `age.agekey` in the Kubernetes Secret; other names are silently ignored
- SOPS does not encrypt YAML comments — do not put sensitive values in comments adjacent to encrypted fields
- `encrypted_regex` matches YAML keys, not values — `^(data|stringData)$` encrypts all values under those keys
- Running `sops --decrypt` to stdout in CI must be followed by masking the output in the step; GitHub Actions `::add-mask::` only applies to subsequent steps

## Verification
```bash
# Confirm no plaintext secrets in encrypted file
grep -E "(password|apiKey|token)" k8s/production/db-credentials.enc.yaml \
  | grep -v "ENC\[" && echo "FAIL: unencrypted value" || echo "OK"

# Decrypt and verify structure (requires private key)
SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt \
  sops --decrypt k8s/production/db-credentials.enc.yaml | kubectl apply --dry-run=server -f -

# Verify Flux decryption is working
kubectl get kustomization production-secrets -n flux-system -o jsonpath='{.status.conditions}'
```

## Related
- `/documentation/docs/policies/infra/secrets-management-comparison.md`
- `/documentation/docs/policies/infra/gitops-argocd-flux.md`
- `/documentation/docs/policies/infra/workers-secrets-rotation-automation.md`
- `/documentation/docs/policies/infra/vault-cloudflare-workers-dynamic-secrets.md`

## Sources
- https://github.com/getsops/sops
- https://github.com/FiloSottile/age
- https://fluxcd.io/flux/guides/mozilla-sops/
- https://fluxcd.io/flux/components/kustomize/kustomizations/#decryption
- https://getsops.io/docs/#using-sops-with-age
