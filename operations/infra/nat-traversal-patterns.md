# nat-traversal-patterns

**Issue:** Peers behind home routers, mobile carriers, and cloud VPCs cannot receive inbound connections because NAT rewrites addresses and drops unsolicited packets, which breaks direct peer-to-peer connections for WebRTC media, game servers, self-hosted services, and agent-to-agent mesh traffic. This article covers how NAT behaviors classify the problem, the STUN/TURN/ICE toolkit used to solve it, how to design a traversal stack where direct connections succeed for most peers with a relay fallback for the rest, and the operational failure modes (symmetric NAT, CGNAT, mapping timeouts) that cause "it works from my house but not from the office" bugs.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## NAT Behaviors That Classify the Problem

1. **Endpoint-independent mapping (full-cone NAT).** The NAT reuses the same external port for all destinations once a mapping exists, so after the peer sends one outbound packet, anyone who knows the public `ip:port` can reach it — the easiest case, and hole punching works reliably.
2. **Address-restricted and port-restricted filtering.** The NAT reuses one mapping but only forwards inbound packets whose source matches a destination the internal host has already contacted (address-restricted checks the IP, port-restricted also checks the source port). Hole punching still works because both peers send first, satisfying the filter from both sides.
3. **Symmetric NAT: mapping per destination.** The NAT assigns a different external port for every destination the internal host contacts, so the public address learned via STUN against server A tells you nothing about the port that will be seen by peer B. Standard UDP hole punching fails here, and industry measurements consistently put direct-connection failure on double-symmetric pairs as the dominant residual case.
4. **CGNAT multiplies symmetric behavior.** Carrier-grade NAT stacks hundreds of subscribers behind one public IP with per-destination mappings, so mobile networks are effectively large symmetric NATs; port prediction and birthday-attack techniques (probing many ports to hit the mapped one probabilistically) recover some connections but never reliably.
5. **Mapping lifetime is a first-class constraint.** NAT mappings expire after an idle timeout (commonly 30–120 seconds for UDP, sometimes minutes for TCP), so any traversal design must include keepalives shorter than the observed timeout or the hole silently closes mid-session. RFC 4787 standardized this vocabulary (mapping behavior, filtering behavior, timeouts) so you can classify a network instead of guessing.

## The Traversal Toolkit

1. **STUN for public address discovery.** A STUN server (RFC 8489 for the standalone protocol) echoes back the observed `ip:port` so a peer behind NAT learns its server-reflexive candidate; this is cheap, stateless, and typically the first step in every traversal flow.
2. **Hole punching via simultaneous open.** Both peers exchange candidates through a signaling channel and then send packets to each other at the same time, so each outbound packet opens its local NAT exactly when the peer's inbound packet arrives — this resolves the majority of connections without any relay, using nothing but UDP.
3. **ICE for candidate orchestration.** Interactive Connectivity Establishment gathers all candidates (host, server-reflexive/STUN, relay/TURN), pairs them, runs priority-ordered connectivity checks in both directions, and nominates the best working pair — and it can restart mid-session if the network path changes. Never hand-roll the pairing logic; use libjuice, usrsctp, aiortc, or the browser's built-in WebRTC stack.
4. **TURN relays as the guaranteed fallback.** When direct connection is impossible (double symmetric NAT, hostile firewalls), a TURN server relays all traffic, trading cost and latency for certainty. Production systems report roughly 10–20% of sessions needing TURN, so TURN capacity planning (bandwidth, ports, geographic placement) is a real cost line, not an afterthought.
5. **Modern stacks add multiplexing and QUIC.** Newer systems (Iroh, libp2p's DCUtR, multiplexed TURN allocations) multiplex many sessions over one relay connection or run traversal over QUIC, which avoids TCP head-of-line blocking and handles address migration natively; Tailscale's DERP relays are the canonical example of a purpose-built encrypted relay fallback network.

## Designing a Traversal Stack

1. **Separate signaling from data.** Candidates and authentication material are exchanged out-of-band (WebSocket to your API, libp2p, a database row), while the data path goes direct or through relay; the signaling server sees metadata but never payloads, which keeps it cheap and low-risk.
2. **Gather candidates in parallel, prefer direct.** Collect host, srflx, and relay candidates simultaneously, attempt direct pairs first, and only fall back to relay when checks fail or time out — falling back too early wastes TURN bandwidth on sessions that would have connected in another 500 ms.
3. **Keepalives tuned below the mapping timeout.** Send a small keepalive (STUN binding indication or application ping) every 15–25 seconds on the active path to hold both NAT mappings; also keep the ICE consent mechanism alive so a dead path is detected within seconds rather than after a user-visible hang.
4. **Make relay fallback automatic and invisible.** If direct connectivity checks fail within your timeout budget, promote the relay candidate without user action, and periodically re-attempt direct (ICE restart) since NAT mappings on either end may change — mobile peers change networks constantly.
5. **Instrument success rates per network type.** Log which candidate type won (host/srflx/relay), the peers' detected NAT behaviors, and time-to-connect; without these metrics you cannot tell whether a rise in relay usage is a TURN cost problem, a carrier NAT change, or a bug in your candidate gathering.

## Operational Pitfalls

1. **Symmetric NAT on both ends cannot be punched.** No amount of STUN retrying fixes double-symmetric pairs where each side's port depends on the destination; accept it, detect it early (the candidate checks will fail from multiple ports), and route those sessions to relay instead of burning seconds in futile retries.
2. **Hard-coded STUN/TURN credentials and ports rot.** Shared TURN secrets, time-windowed credentials (`TURN REST API` style), and port ranges must be provisioned consistently across coturn config and client code; a stale secret produces silent relay failure that looks identical to "symmetric NAT" in symptoms.
3. **TCP hole punching is real but fragile.** Simultaneous TCP open (both sides SYN at once) works through some NATs but is defeated by many middleboxes and SYN proxies; treat TCP traversal as a last resort behind UDP, and never rely on it as the only path.
4. **Enterprise firewalls do more than NAT.** Deep-packet inspection, UDP blocking, and TLS-only egress policies punch holes in assumptions — a fallback path over WebSocket/TLS or QUIC on port 443 (the DERP model) is what keeps those users connected at all.
5. **Relay bandwidth is the cost center.** Every relayed media or file-transfer session pays egress twice; enforce per-session bandwidth caps, place relays near user concentrations, and alarm on the relayed-session percentage — a silent climb from 15% to 40% relayed is both a budget and a UX regression signal.
