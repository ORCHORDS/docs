# IETF BGP-4 Operational Stability (RFC 4271)

## Purpose

Border Gateway Protocol version 4 (BGP-4) is the inter-domain routing protocol that makes autonomous-system-level policy decisions across the public Internet. RFC 4271 is the base specification of BGP-4. Operational use of BGP-4 depends on a small set of behaviors in the protocol that, when misconfigured, become stability hazards. This article summarizes the operational properties of BGP-4 relevant to stability and security operations, beyond what the per-protocol RFC 9234 route-leak guidance covers.

## Protocol position

BGP is a path-vector protocol. It carries reachability information together with the AS path that the reachability advertisement has traversed. Every BGP speaker processes incoming advertisements against locally configured policies. Because BGP carries reachability for the entire Internet and its policy outcomes affect traffic flow globally, the protocol's behavior is sensitive to local policy, not only to local configuration errors.

The basic message types — OPEN, UPDATE, NOTIFICATION, KEEPALIVE, and ROUTE-REFRESH — are defined in RFC 4271. The base protocol assumes TCP (port 179) as transport, and it is the responsibility of operators to provide the underlying connectivity that sessions depend on.

## Operational dependencies

BGP does not produce a "best" route that is universally correct. Each speaker applies its own local preference, AS path length, MED, IGP metric, eBGP over iBGP, router-id, and tiebreaker rules. The operationally important consequence is that a single topology change can produce different decisions on different speakers, including transient divergence until the protocol reconverges.

BGP timers matter. Hold-time and keepalive are configured per peer, with rules around reset on mismatch; the route damping mechanism defined in RFC 4271 was deprecated by RFC 8004 and should not be used operationally anymore.

## Stability properties

The behaviors that drive BGP stability are:

- **Path tracking** — BGP keeps path attributes per prefix, so the protocol can withdraw and re-advertise specific paths.
- **Route selection** — BGP's tiebreaker chain produces a single best path; everything else is held as alternate information.
- **Convergence time** — convergence can take minutes to tens of minutes under stress, so stability of reachability is the property that operators care about.
- **Convergence-amplification** — minor events can produce many more messages when many prefix churn concurrently.

Operationally, the protocols surrounding BGP — for example BFD and TCP-AO — exist precisely to address recovery time and to protect the BGP session itself, and they should be configured deliberately rather than only enabled by default.

## Operational workflow

1. Document the network topology and the intended BGP relationships at each edge (customer, peer, transit, route server).
2. Configure inbound and outbound policies per relationship; record the rationale and the policy owner.
3. Apply max-prefix limits per peer and per session; configure alarms at a fraction of the limit so the limit is never approached without warning.
4. Use route refresh only where the neighbor supports it; never rely on route refresh as a substitute for regular session state monitoring.
5. Enable BFD for fast failure detection where the topology permits, and treat BFD flapping as a network signal rather than as a configuration nuisance.
6. Maintain a current IRR/RPKI view for each session so that filters reflect current intent.
7. Treat routing changes as change-controlled work: announce, then validate prefix lists, RPKI status, and AS-path expectations.
8. Plan for partial withdrawal by validating impact under simulated propagation before deploying a new filter or session.

## Validation evidence

Retain session topology, peer-type and AS-path policies, max-prefix configurations and alarm thresholds, change records for prefix-list changes, route-alerting and damping history, BFD and TCP-AO configuration, IRR/RPKI inputs that justified the policy, and incident post-mortem records. Validation should include live peer confirmation, because a session that has been administratively up for years may still hold stale policy.

## Failure modes

Failure modes include max-prefix alarms being treated as noise and ignored, route flap damping being reintroduced and degrading stability, RPKI/IRR data being ignored so that invalid-prefix advertisements pass filters, and missing route refresh expectations producing cryptic operational issues. These failures often surface as "BGP is slow" complaints during incidents rather than as discrete events.

## Interaction with route security frameworks

Operational stability depends on more than the protocol itself; it depends on the integrity of the information that the protocol consumes. RPKI provides cryptographically signed statements about route origin authorization so that a BGP speaker can reject advertisements from unauthorized AS origins. IRR objects document intended peerings, prefix limits, and AS-path information. Together, RPKI and IRR provide the security inputs the base protocol does not enforce by itself. Operations teams should treat the input data as configuration, validate it regularly, and version it alongside other policy artifacts.

## Working with incident response

BGP incidents are usually adjacent to other incidents. The routing team should be reachable as a named participant in the broader incident response model, not as a back-channel contacted after hours. During multi-team incidents the role is parallel to the security, platform, and service roles, with its own statement of work and its own evidence expectations. Post-incident reviews involving routing changes should preserve the BGP session state at the moment of the event, not only the eventual resolution, so the next decision maker benefits from the same facts.

## Canonical sources

- RFC 4271, A Border Gateway Protocol 4 (BGP-4): https://www.rfc-editor.org/rfc/rfc4271
- RFC 9234, BGP Route Leaks: https://www.rfc-editor.org/rfc/rfc9234
- RFC 7454, BGP Operations and Security (BCP 194): https://www.rfc-editor.org/rfc/rfc7454

## Scope note

This article summarizes RFC 4271 and adjacent operations guidance; specific Internet exchange points, transit provider conventions, and regional addressing policy remain separate operational topics.
