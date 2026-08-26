# kubernetes-cert-manager

**Issue:** Automating TLS certificate issuance and renewal with cert-manager
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Manual TLS certificate management causes outages when certs expire. cert-manager automates issuance from Let's Encrypt, Vault, or private CAs and handles renewal before expiry.

## Pattern / Solution
Install cert-manager:
```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml
kubectl wait --for=condition=Available deploy -n cert-manager --all --timeout=120s
```

ClusterIssuer for Let's Encrypt (ACME HTTP-01):
```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: ops@example.com
    privateKeySecretRef:
      name: letsencrypt-prod-key
    solvers:
    - http01:
        ingress:
          class: nginx
```

DNS-01 challenge for wildcard certs (Route53):
```yaml
    solvers:
    - dns01:
        route53:
          region: us-east-1
          hostedZoneID: Z1234567890
          accessKeyIDSecretRef:
            name: route53-credentials
            key: access-key-id
          secretAccessKeySecretRef:
            name: route53-credentials
            key: secret-access-key
```

Manually create a Certificate:
```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: myapp-tls
  namespace: production
spec:
  secretName: myapp-tls
  issuerRef:
    name: letsencrypt-prod
    kind: ClusterIssuer
  dnsNames:
  - myapp.example.com
  - "*.myapp.example.com"
```

Check cert status:
```bash
kubectl describe certificate myapp-tls -n production
kubectl get certificaterequest -n production
cmctl status certificate myapp-tls -n production
```

## Gotchas
- Let's Encrypt rate limit: 5 certificates per registered domain per week; use staging issuer for testing
- HTTP-01 challenge requires the Ingress to be accessible on port 80 from the internet
- Cert renewal starts 30 days before expiry by default; do not delete the Secret or cert-manager loses its renewal anchor
- `CertificateRequest` objects pile up over time; prune with `kubectl delete certificaterequest -n ns --field-selector=status.conditions[0].type=Ready`
- Vault issuer requires the cert-manager service account to have Vault auth policy

## Related
- `kubernetes-ingress-controller.md`
- `kubernetes-service-mesh-istio.md`
- `secrets-in-deploy-2026.md`
