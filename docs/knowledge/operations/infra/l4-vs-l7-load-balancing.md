# l4-vs-l7-load-balancing

**Issue:** "Which load balancer should we put in front of the service?" hides a more fundamental question: should balancing happen at layer 4 (TCP/UDP streams) or layer 7 (HTTP semantics)? The choice determines whether you can route by URL path, whether TLS terminates at the balancer or passes through end-to-end, whether WebSocket and gRPC long-lived streams behave, how much client-IP information survives the hop, and how much CPU per connection the balancer burns. Picking the wrong layer produces architecture rework: L4 pass-through boxes that later need header-based routing must be replaced, not reconfigured, and L7 proxies under raw TCP (database, SMTP) traffic simply cannot do the job. This is a per-tier decision that deserves the same rigor as database or cache selection.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What each layer actually does

1. **L4 balances bytes on streams.** A layer-4 balancer sees a TCP or UDP flow, picks a backend by IP, port, or source-hash, and forwards packets or proxies the raw stream. It never parses the payload, so per-connection CPU cost is tiny and protocol-agnostic: databases, SMTP relays, game servers, MQTT, and Kubernetes NodePort-style traffic all work unchanged.

2. **L7 speaks the application protocol.** A layer-7 HTTP balancer terminates the client TCP connection, parses requests, and opens a second connection upstream — a full proxy with two distinct TCP sessions per client. In exchange it can route by path, host, header, or cookie, rewrite URLs, terminate TLS, compress responses, cache, and run WAF-style inspection.

3. **The two-connection model has consequences.** Because L7 splits the client and backend legs, it can apply different protocols on each (HTTP/3 to the client, HTTP/1.1 to a legacy backend) and different keepalive policies — but it also means backend connection state, client IP, and TLS identity do not flow through naturally and must be re-injected explicitly.

4. **Throughput and latency floors differ.** L4 balancers sustain more raw throughput and add less latency because they do shallow work per packet; L7 balancers burn CPU parsing and buffering. At modest scale both are effectively free; at carrier scale (hundreds of thousands of concurrent streams) the gap decides hardware budgets.

## Selection criteria

1. **Route by anything other than IP or port: L7.** If requirements mention path-based routing (/api to one service, /admin to another), header-based canary selection, or sticky sessions via cookie, only layer 7 can see those signals.

2. **Terminate TLS centrally: L7.** Certificate management, HTTP/3 to clients, TLS 1.3 policy, and request inspection all argue for terminating at an L7 tier. L4 pass-through (SNI-based routing aside) pushes certificate lifecycle onto every backend, which does not scale operationally.

3. **Preserve TLS end-to-end (compliance, mTLS): L4.** Payment PCI scopes and zero-trust mTLS interiors often require the backend to see the client's real certificate and terminate its own TLS; there, L4 with SNI-based routing (Envoy, HAProxy ssl-hello-less SNI matchers, or a TCP proxy) is the standard pattern.

4. **Non-HTTP protocols: L4, full stop.** PostgreSQL, Redis, Kafka, LDAP, and SMTP cannot be balanced by an HTTP proxy; the only choices there are L4 balancing or the protocol's native discovery.

5. **Long-lived streams (WebSockets, gRPC): either, with caveats.** L4 passes streams trivially. L7 works but requires explicit idle-timeout and max-connection-duration tuning, and gRPC benefits from L7 awareness (HTTP/2 keepalives, per-RPC load balancing across multiplexed streams rather than per-connection).

## Client IP preservation

1. **L7: inject the client IP into headers.** X-Forwarded-For and X-Real-IP carry the original address; configure the proxy to append (not overwrite) XFF at every trusted hop and strip it from untrusted inbound requests to prevent spoofing.

2. **L4 pass-through: the source IP survives naturally.** True packet-pass-through (DNAT) modes keep the client source address on the wire reaching the backend — the cheapest correct answer, at the cost of backend routing complexity (return-path asymmetry needs DSR or matching routing).

3. **L4 proxy mode: use PROXY protocol.** When the L4 balancer terminates and re-originates TCP, the backend would otherwise see only the balancer's IP. PROXY protocol (v1 text, v2 binary with IPv6 and Unix-socket support) prepends the real source address to the stream. The hard constraint: every downstream hop must understand it — enabling it against a backend that does not expect it corrupts the stream, and it must be enabled end-to-end through chained proxies.

4. **Cloud NLBs: check the mode, not the name.** AWS NLB and equivalents offer client-IP-preservation per target-group type, but preservation interacts with connection reuse and security-group behavior differently per mode; verify with a tcpdump or a whoami endpoint before assuming rate-limiting by client IP will work.

## Layered topology patterns

1. **L4 edge, L7 internal.** A common production shape: an L4 balancer (or cloud NLB) fronts multiple L7 proxies across AZs for availability, while the L7 tier does TLS termination, routing, and WAF. Each layer does the job it is efficient at.

2. **Keep health checks honest per layer.** An L4 health check proves the TCP stack is alive, not that the application can serve; pair L4 checks on the balancer with deep HTTP checks in the monitoring stack so a wedged app is not marked healthy because its port answers.

3. **Avoid balancing the same pool at two layers.** Double-balancing (L4 spreading over L7 instances that each spread over all app instances) multiplies connection fan-out and hides per-instance load from both layers; give each layer distinct, non-overlapping pools or make one layer a passthrough.

4. **Plan fail-open versus fail-closed per layer.** L7 tiers can serve cached or maintenance responses when all backends fail; L4 tiers have no such concept and simply refuse connections. Which behavior users see during a backend outage is an architectural decision made here, not during the incident.
