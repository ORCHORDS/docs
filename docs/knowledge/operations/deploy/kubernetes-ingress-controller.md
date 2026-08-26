# kubernetes-ingress-controller

**Issue:** Configuring ingress controllers for TLS termination, routing, and traffic management
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Kubernetes Services are cluster-internal; Ingress exposes HTTP/HTTPS routes to the outside world. Choice of controller (NGINX, Traefik, Gateway API) affects features and operational complexity.

## Pattern / Solution
NGINX Ingress with TLS:
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: myapp
  namespace: production
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/rate-limit: "100"
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  ingressClassName: nginx
  tls:
  - hosts: [myapp.example.com]
    secretName: myapp-tls
  rules:
  - host: myapp.example.com
    http:
      paths:
      - path: /api
        pathType: Prefix
        backend:
          service:
            name: api-service
            port:
              number: 8080
      - path: /
        pathType: Prefix
        backend:
          service:
            name: frontend-service
            port:
              number: 80
```

Kubernetes Gateway API (newer standard):
```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: myapp
spec:
  parentRefs:
  - name: prod-gateway
  hostnames: ["myapp.example.com"]
  rules:
  - matches:
    - path:
        type: PathPrefix
        value: /api
    backendRefs:
    - name: api-service
      port: 8080
```

Canary routing via NGINX annotation:
```yaml
annotations:
  nginx.ingress.kubernetes.io/canary: "true"
  nginx.ingress.kubernetes.io/canary-weight: "10"   # 10% of traffic
```

## Gotchas
- Multiple Ingress objects for the same host must use the same `ingressClassName`; conflicts cause unpredictable routing
- `pathType: Exact` vs `Prefix` matters — `/api` Exact does not match `/api/users`
- TLS secret must be in the same namespace as the Ingress (or use ClusterSecretStore)
- NGINX buffer sizes default to 4k/8k; large request bodies or headers need `proxy-buffer-size` tuning
- Gateway API requires installing CRDs separately from the controller; version mismatches cause silent failures

## Related
- `kubernetes-cert-manager.md`
- `kubernetes-service-mesh-istio.md`
- `canary-deployments.md`
