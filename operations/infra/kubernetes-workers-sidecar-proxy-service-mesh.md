# Cloudflare Workers as a Sidecar Proxy in Kubernetes Service Meshes

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Teams running Kubernetes workloads want to offload TLS termination, request routing, and
authentication to Cloudflare Workers rather than maintaining Istio or Linkerd data-plane sidecars
in every pod. The challenge is bridging the Cloudflare edge to internal K8s services without
punching public holes in the cluster or deploying heavyweight control-plane components.

## Context

Cloudflare Workers can act as an L7 proxy in front of Kubernetes services, handling ingress,
mTLS negotiation, JWT validation, and rate-limiting at the edge before traffic ever reaches the
cluster. The linkage between the Workers edge and the K8s cluster is established via Cloudflare
Tunnel (`cloudflared`), which runs as a Deployment in the cluster and opens outbound-only
connections to Cloudflare's anycast network. This avoids exposing a LoadBalancer or NodePort to
the internet. For east-west (pod-to-pod) traffic inside the cluster, Workers Unbound can proxy
cross-namespace calls through the same tunnel, replacing service-mesh sidecars for workloads
whose traffic is already being proxied at the Cloudflare edge.

## Cloudflare Tunnel as the K8s Ingress Backbone

Deploy `cloudflared` as a Kubernetes Deployment with an auto-scaling HPA. The Tunnel maps
hostnames to in-cluster Service addresses:

```yaml
# cloudflared-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cloudflared
  namespace: infra
spec:
  replicas: 2
  selector:
    matchLabels:
      app: cloudflared
  template:
    metadata:
      labels:
        app: cloudflared
    spec:
      containers:
        - name: cloudflared
          image: cloudflare/cloudflared:2026.8.0
          args:
            - tunnel
            - --config
            - /etc/cloudflared/config.yaml
            - run
          volumeMounts:
            - name: config
              mountPath: /etc/cloudflared
              readOnly: true
            - name: creds
              mountPath: /etc/cloudflared/creds
              readOnly: true
          resources:
            requests:
              cpu: "100m"
              memory: "64Mi"
            limits:
              cpu: "500m"
              memory: "128Mi"
      volumes:
        - name: config
          configMap:
            name: cloudflared-config
        - name: creds
          secret:
            secretName: cloudflared-tunnel-creds
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: cloudflared-config
  namespace: infra
data:
  config.yaml: |
    tunnel: <TUNNEL_UUID>
    credentials-file: /etc/cloudflared/creds/credentials.json
    ingress:
      - hostname: api.example.com
        service: http://api-service.default.svc.cluster.local:8080
      - hostname: admin.example.com
        service: http://admin-service.default.svc.cluster.local:9090
      - service: http_status:404
```

## Workers as the L7 Proxy Layer — mTLS, Auth, and Routing

A Worker sits in front of the Tunnel, applying authentication, rate limiting, and routing logic
before forwarding to the cluster. The Worker's `fetch` handler acts as the proxy:

```typescript
interface Env {
  UPSTREAM_TUNNEL: string;     // e.g. "https://api.example.com" — routed via Tunnel
  JWT_PUBLIC_KEY: string;      // RS256 public key PEM for JWT verification
  RATE_LIMIT: RateLimit;       // Cloudflare Rate Limiting binding
}

async function verifyJWT(token: string, publicKeyPem: string): Promise<boolean> {
  // Import the RS256 public key
  const key = await crypto.subtle.importKey(
    "spki",
    pemToDer(publicKeyPem),
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["verify"],
  );

  const [headerB64, payloadB64, sigB64] = token.split(".");
  const data = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
  const sig = base64urlDecode(sigB64);

  return crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, sig, data);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // 1. Rate limiting — keyed by CF-Connecting-IP
    const { success } = await env.RATE_LIMIT.limit({ key: request.headers.get("CF-Connecting-IP") ?? "anon" });
    if (!success) return new Response("Too Many Requests", { status: 429 });

    // 2. JWT authentication
    const authHeader = request.headers.get("Authorization");
    if (!authHeader?.startsWith("Bearer ")) {
      return new Response("Unauthorized", { status: 401 });
    }
    const valid = await verifyJWT(authHeader.slice(7), env.JWT_PUBLIC_KEY);
    if (!valid) return new Response("Forbidden", { status: 403 });

    // 3. Strip internal headers, forward to K8s service via Tunnel
    const upstreamUrl = new URL(request.url);
    upstreamUrl.hostname = new URL(env.UPSTREAM_TUNNEL).hostname;

    const upstreamRequest = new Request(upstreamUrl.toString(), {
      method: request.method,
      headers: filterHeaders(request.headers),
      body: request.body,
    });

    const response = await fetch(upstreamRequest);
    return new Response(response.body, {
      status: response.status,
      headers: addSecurityHeaders(response.headers),
    });
  },
};

function filterHeaders(headers: Headers): Headers {
  const filtered = new Headers(headers);
  // Strip hop-by-hop and internal headers before forwarding
  for (const h of ["x-internal-token", "cf-connecting-ip", "x-forwarded-for"]) {
    filtered.delete(h);
  }
  return filtered;
}

function addSecurityHeaders(headers: Headers): Headers {
  const out = new Headers(headers);
  out.set("Strict-Transport-Security", "max-age=31536000; includeSubDomains");
  out.set("X-Content-Type-Options", "nosniff");
  return out;
}
```

## Zero Trust Tunnel to K8s Pods — Per-Pod mTLS

For scenarios requiring per-pod identity (zero-trust east-west), use Cloudflare Zero Trust with
service tokens and a `cloudflared` sidecar per pod (lightweight alternative to Istio Envoy):

```yaml
# Pod spec with cloudflared sidecar for zero-trust east-west
spec:
  containers:
    - name: app
      image: myapp:latest
      env:
        - name: UPSTREAM
          value: "http://localhost:8081"  # sidecar proxy
    - name: cloudflared-sidecar
      image: cloudflare/cloudflared:2026.8.0
      args:
        - access
        - tcp
        - --hostname=internal-db.example.com
        - --url=localhost:5432
      env:
        - name: TUNNEL_SERVICE_TOKEN_ID
          valueFrom:
            secretKeyRef:
              name: cf-service-token
              key: id
        - name: TUNNEL_SERVICE_TOKEN_SECRET
          valueFrom:
            secretKeyRef:
              name: cf-service-token
              key: secret
      resources:
        requests:
          cpu: "50m"
          memory: "32Mi"
        limits:
          cpu: "200m"
          memory: "64Mi"
```

The app container connects to `localhost:5432` — the sidecar tunnels that connection through
Cloudflare Access to the target service, enforcing service-token authentication and mutual TLS
transparently without any changes to the app code.

## Workers-Native vs Istio/Linkerd — Comparison

| Feature | Workers + CF Tunnel | Istio | Linkerd |
|---|---|---|---|
| Sidecar overhead | Optional, ~32 MiB | Envoy, ~50–150 MiB/pod | micro-proxy, ~10 MiB/pod |
| Control plane | Cloudflare edge (managed) | istiod (self-managed) | linkerd-control-plane |
| mTLS | Via CF Access service tokens | SPIFFE/SVID auto-rotation | SPIFFE/SVID auto-rotation |
| Ingress | Workers route → Tunnel | Istio Gateway / VirtualService | nginx + SMI |
| Observability | Workers Analytics + Tail Workers | Kiali, Jaeger integration | Viz dashboard, Prometheus |
| Policy language | Workers JS/TS, CF Rules | AuthorizationPolicy YAML | Server/HTTPRoute |
| Egress control | CF Gateway CASB | Sidecar + ServiceEntry | Traffic shaping via SMI |
| Best fit | Edge-heavy, globally distributed apps | Complex K8s-native service graphs | Lightweight K8s-only meshes |

## Hybrid Edge + K8s Architecture

The recommended hybrid pattern routes public traffic through Workers for edge logic (geo-routing,
bot management, caching), then hands off to K8s services through the Tunnel for application
logic. Internal K8s pod-to-pod traffic uses standard Kubernetes NetworkPolicies or Linkerd for
east-west, reserving Workers for north-south edge concerns:

```
Internet
  │
  ▼
Cloudflare Workers (auth, rate-limit, WAF, geo-block)
  │  HTTPS via Cloudflare Tunnel
  ▼
cloudflared Deployment (K8s namespace: infra)
  │  ClusterIP Service
  ▼
Application Pods (namespace: default)
  │  Linkerd mTLS (east-west only)
  ▼
Database / Cache Pods
```

Pulumi resource graph for the hybrid stack:

```typescript
import * as cloudflare from "@pulumi/cloudflare";
import * as k8s from "@pulumi/kubernetes";

// Cloudflare Tunnel
const tunnel = new cloudflare.Tunnel("k8s-tunnel", {
  accountId: process.env.CF_ACCOUNT_ID!,
  name: "k8s-prod",
  secret: process.env.TUNNEL_SECRET!,
});

// DNS CNAME pointing to the tunnel
new cloudflare.Record("api-cname", {
  zoneId: process.env.CF_ZONE_ID!,
  name: "api",
  type: "CNAME",
  value: tunnel.cname,
  proxied: true,
});

// K8s Secret with tunnel credentials
new k8s.core.v1.Secret("cloudflared-creds", {
  metadata: { name: "cloudflared-tunnel-creds", namespace: "infra" },
  stringData: {
    "credentials.json": tunnel.tunnelToken.apply(t => JSON.stringify({ AccountTag: "", TunnelID: tunnel.id, TunnelSecret: t })),
  },
});
```

## Anti-patterns

- Running `cloudflared` as a DaemonSet instead of a Deployment — DaemonSet places a tunnel
  process on every node, wasting resources. Use a Deployment with 2–4 replicas for HA.
- Exposing a K8s LoadBalancer (public IP) alongside the Cloudflare Tunnel — the tunnel becomes
  a false sense of security if the service is reachable directly. Restrict LoadBalancer to
  cluster-internal or use `externalTrafficPolicy: Local` plus firewall rules.
- Using Workers as east-west (pod-to-pod) proxies for high-throughput internal RPC — every call
  exits the cluster, traverses Cloudflare's network, and re-enters via the tunnel; this adds
  30–100 ms per hop and is far more expensive than a in-cluster service mesh.
- Skipping NetworkPolicies inside the cluster when using CF Tunnel for ingress — the tunnel
  secures the ingress path but does not restrict lateral movement once a pod is compromised.
- Storing `credentials.json` in a plain K8s ConfigMap — always use a Secret (or External Secrets
  Operator backed by Vault/AWS SSM) so credentials are not included in ConfigMap backups.

## Gotchas

- `cloudflared` versions are tied to Cloudflare protocol versions; pin a specific image tag and
  test upgrades in staging. The `latest` tag has broken production tunnels on minor releases.
- Cloudflare Tunnel supports HTTP/1.1 and HTTP/2 to the origin; HTTP/3 (QUIC) to the origin is
  not yet supported. If your K8s service speaks gRPC (HTTP/2), ensure the tunnel config sets
  `originServerName` and `noTLSVerify: false` with a valid in-cluster cert.
- Workers have a 128 MB memory limit and a 30 s CPU wall time. Proxying large streaming
  responses (e.g., file downloads) through a Worker will buffer the body in memory and can hit
  both limits. Use `TransformStream` or `response.body` streaming and avoid `await res.text()`.
- Cloudflare Zero Trust Access policies evaluated in the Worker's `fetch` path add ~5–10 ms
  per request. Cache the JWT validation result in a Workers KV entry keyed by token hash with a
  TTL matching the token's `exp` claim.

## Verification

```bash
# Confirm tunnel is active and connected
cloudflared tunnel info k8s-prod

# List active tunnel connections (should show 4 connections for HA)
cloudflared tunnel connections k8s-prod

# Test routing from outside — expect 200 from K8s backend
curl -si https://api.example.com/healthz

# Check cloudflared pod logs in K8s
kubectl logs -n infra -l app=cloudflared --tail=50

# Validate NetworkPolicy is blocking direct pod access
kubectl run test-pod --rm -it --image=curlimages/curl -- \
  curl -si http://api-service.default.svc.cluster.local:8080/healthz

# Verify mTLS with Zero Trust service token
curl -si \
  -H "CF-Access-Client-Id: ${CF_CLIENT_ID}" \
  -H "CF-Access-Client-Secret: ${CF_CLIENT_SECRET}" \
  https://internal-db.example.com
```

## Related

- `infra/cloudflare-tunnel-private-services.md`
- `infra/kubernetes-network-policies-service-mesh.md`
- `infra/k8s-gateway-api.md`
- `infra/cloudflare-zero-trust-staging-prod-isolation.md`
- `infra/pulumi-cloudflare-workers-infrastructure-as-code.md`
- `infra/service-mesh-ambient-sidecar.md`

## Sources

- https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
- https://developers.cloudflare.com/workers/runtime-apis/fetch/
- https://developers.cloudflare.com/cloudflare-one/applications/non-http/
- https://istio.io/latest/docs/concepts/what-is-istio/
- https://linkerd.io/2.15/overview/
- https://developers.cloudflare.com/cloudflare-one/identity/service-tokens/
