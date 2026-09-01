# Load Balancer L4 Vs L7 Routing Decision

## Scope

This article addresses the engineering decision between Layer 4 (L4) and Layer 7 (L7) load balancing. It explains what each layer balances, what information is available to the load balancer at each layer, and what trade-offs follow from that information. The discussion covers transport-layer balancing (TCP, UDP), application-layer balancing (HTTP, HTTP/2, HTTP/3, gRPC), the trade-offs in latency, termination, observability, and protocol awareness, and the deployment patterns that mix the two. The article applies to any system that distributes traffic across multiple backends, including AWS Elastic Load Balancing, Cloudflare Load Balancer, HAProxy, NGINX, Envoy, and Kubernetes Ingress.

## Workflow or implementation guidance

A Layer 4 load balancer makes its routing decision based on the transport-layer information: source IP and port, destination IP and port, and the protocol (TCP, UDP, sometimes SCTP). It does not parse the application payload. A Layer 7 load balancer parses the application protocol (HTTP, HTTP/2, gRPC, MQTT) and makes its routing decision based on the application-layer information: host, path, headers, method, cookies, query string, and (for gRPC) the service and method.

The first step in the decision is to ask what routing dimension the workload needs. If the answer is "all traffic to one backend," a DNS-level load balancer (Route 53, Cloudflare DNS) is sufficient and is not in scope. If the answer is "TCP traffic across N backends by source IP," an L4 load balancer is sufficient. If the answer is "HTTP traffic with routing by host or path," an L7 load balancer is necessary.

The second step is to consider latency. An L4 load balancer is faster because it does not parse the application payload; it can make its decision after the TCP handshake and start forwarding bytes. An L7 load balancer must read the request line and the headers before making a decision, which adds a small amount of latency. For most workloads this is negligible; for very high-throughput, low-latency workloads (game servers, financial trading), the L4 advantage matters.

The third step is to consider observability and routing richness. An L7 load balancer can route on the URL path, on a header, on a cookie, on the gRPC service name. It can also rewrite the request, add headers, and apply policies based on the application semantics. An L4 load balancer cannot do any of this. If the workload requires "send all `/api/*` to backend pool A and `/images/*` to pool B," an L7 load balancer is required.

The fourth step is to consider TLS termination. An L7 load balancer that supports HTTP can terminate TLS, because TLS termination is part of the HTTP path. An L4 load balancer can also terminate TLS if it is a TLS-aware L4 load balancer (such as AWS NLB with TLS listeners), but the decision is typically based on SNI or on a wildcard certificate, not on the application semantics.

The fifth step is to consider the deployment topology. Many production systems use both: an L4 load balancer at the edge for raw TCP/UDP performance and an L7 load balancer behind it for application-layer routing. This pattern is common in service-mesh deployments (Envoy, Istio) where the sidecar is an L7 proxy and the ingress is an L4 load balancer.

In practice, the decision is rarely "L4 or L7" and is usually "which L7 features do I need?" because L7 load balancers are a superset of L4 load balancers in capability. The trade-off is purely the small latency cost and the increased operational surface of parsing the application protocol.

## Controls

L4 controls cover connection draining, source-IP preservation, and TCP-level health checks. L7 controls cover HTTP health checks, content-based routing, request rewriting, header injection, rate limiting, and circuit breaking at the application layer. The controls you choose depend on what the load balancer is responsible for: a load balancer that only forwards traffic has minimal controls; a load balancer that is also the policy enforcement point has many.

Observability is different at each layer. L4 metrics focus on bytes per second, packets per second, active connections, and SYN/SYN-ACK rates. L7 metrics focus on requests per second, request duration, status codes, and upstream connection pool health. A system that uses both layers must capture both kinds of metrics and correlate them.

## Validation evidence

Validation must prove that the load balancer distributes traffic correctly across the backends. The standard test sends N requests and asserts that each backend received approximately N/k requests (where k is the number of backends), with no backend overloaded and no backend starved. Validation must also prove that the health checks work: a failing backend is taken out of rotation, and a recovering backend is put back. A more demanding test exercises the routing rules: requests to `/api/*` go to backend A, requests to `/images/*` go to backend B, and a misrouted request is impossible.

Validation must also prove the failover path. A backend is killed mid-traffic, and the load balancer must remove it from the pool without dropping in-flight connections (for L4 with connection draining) or with a graceful error response (for L7).

## Failure modes and correction

The dominant failure is the load balancer being a single point of failure. A single load balancer instance, even a managed one, can become the bottleneck or the failure point of the entire system. The cure is to run multiple load balancer instances behind an anycast IP or behind DNS-based failover. A second failure is the load balancer misrouting traffic because of stale configuration. The cure is to version and review configuration changes, and to use a control plane that validates the configuration before applying it.

A third failure is the load balancer amplifying a backend's failure. A slow backend causes the load balancer's connection pool to fill up, and the load balancer starts refusing new connections. The cure is to implement circuit breaking at the load balancer and to fail fast. A fourth failure is the load balancer's TLS termination misconfigured. The load balancer serves the wrong certificate, or it terminates TLS and re-encrypts to the backend without preserving the original client IP. The cure is to use the PROXY protocol or the HTTP `X-Forwarded-For` header correctly and to audit the certificate chain.

A fifth failure is the L7 load balancer being used as a service mesh. The load balancer becomes a Swiss-army-knife policy enforcement point, and the operational complexity explodes. The cure is to keep the load balancer focused on routing and to delegate policy to a dedicated layer (a service mesh, an API gateway, or the application itself).

## Limitations

L7 load balancers are not magic. They add latency (small but real), they add operational complexity (parsing HTTP/2 frames is harder than parsing TCP segments), and they add a new failure mode (the load balancer can become the bottleneck). They are also vulnerable to bugs in the HTTP parser: a malformed request that the load balancer handles differently from the backend can cause subtle bugs. L4 load balancers are simpler and faster but cannot do any of the routing richness that modern applications need. The decision is ultimately a trade-off between latency, capability, and operational cost, and the right answer depends on the workload.

## Canonical sources

- AWS — *Elastic Load Balancing* documentation, including the L4 (Network Load Balancer) and L7 (Application Load Balancer) feature comparison: https://docs.aws.amazon.com/elasticloadbalancing/latest/application/introduction.html
- AWS — *What Is Load Balancing?* overview article: https://aws.amazon.com/what-is/load-balancing/
- HAProxy Technologies — *HAProxy Documentation*, the reference for L4 and L7 load balancing concepts and the trade-offs between them
- Cloudflare — *What is a load balancer?* learning article, and the Cloudflare Load Balancer product documentation for the edge context
