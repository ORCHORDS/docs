# tunnel-to-home-inference

**Issue:** The home GPU inference box sits behind CGNAT with no public IP and no port-forwarding ability, so it cannot accept inbound connections directly. We exposed it with a Cloudflare quick tunnel (`cloudflared tunnel --url`, the ephemeral `*.trycloudflare.com` flavor) — but quick tunnels are ephemeral and feature-limited, so the working production chain became: Cloudflare edge → quick tunnel → a guard-proxy on a cheap VPS (rate limiting, auth-key check, URL tracking) → home GPU box. The VPS relay exists because the tunnel URL is ephemeral, the GPU box is not directly reachable, and something stable must hold auth and rate-limit policy in front of the model.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The Chain and Why Each Hop Exists

1. **cloudflared solves CGNAT by dialing outbound only.** The tunnel connector establishes outbound connections to Cloudflare's edge, so no public IP, port forward, or UPnP is needed — this is the same property that makes named Cloudflare Tunnels the standard homelab exposure pattern for boxes behind carrier NAT.
2. **The guard-proxy is the stable, public anchor.** The quick tunnel URL changes on every connector restart, so the VPS proxy is the hostname clients actually target; it resolves the current tunnel URL (from a small state store the home box updates on tunnel start) and forwards, giving clients one immortal endpoint in front of a rotating one.
3. **Auth and rate limiting live on the VPS, not the GPU box.** The proxy validates a shared API key and applies per-key rate limits before any request reaches the home network, so a leaked or abused client can be throttled or cut off without touching the inference server or the tunnel.
4. **The home box stays initiator-only.** Every long-lived connection in the chain is dialed from inside the home network (cloudflared outward, state-store updates outward), which keeps the router firewall fully closed to inbound traffic.

## Quick Tunnel Limits That Shaped the Design

1. **Hard cap of 200 in-flight requests, then 429.** The official docs set a concurrent-request limit on quick tunnels; a burst of parallel completions from an agent fleet can actually hit it, which is a second reason the VPS proxy queues and meters requests instead of blindly passing them through.
2. **No Server-Sent Events support on quick tunnels.** Current Cloudflare docs state plainly that quick tunnels do not support SSE — so streaming `/v1/chat/completions` responses must either be buffered/re-chunked by the guard-proxy or switched to non-streaming mode through the tunnel hop; this is a hidden trap for exactly the LLM-proxy use case we run.
3. **No SLA, and it is a test surface.** Cloudflare explicitly positions trycloudflare for testing and development, runs new tunnel features on those free connections, and guarantees no uptime — acceptable for a hobby lane, unacceptable as the only path to production traffic.
4. **URL churn is guaranteed, not occasional.** Every `cloudflared tunnel --url` invocation mints a fresh random subdomain, so anything long-lived (webhooks, scheduled agents, the OpenAI-compat gateway's upstream config) must resolve the tunnel dynamically rather than caching a hostname.
5. **A stray `config.yaml` silently breaks quick tunnels.** If `~/.cloudflared/config.yaml` exists, quick-tunnel runs misbehave; this cost an afternoon of debugging before we started isolating the quick-tunnel invocation in its own environment.

## What the Guard-Proxy Actually Does

1. **Key check at the front door.** One shared auth key (rotatable without touching the GPU box), rejected with a generic 401 that leaks nothing about the backend.
2. **Rate limiting per key.** Token-bucket on requests and a concurrency cap sized to the GPU box (one completion at a time for the small model), returning OpenAI-shaped 429s so client SDKs back off automatically instead of hammering the tunnel toward its 200-request ceiling.
3. **Tunnel-URL resolution and health.** The proxy reads the current trycloudflare hostname from the state store, probes it with a cheap health endpoint, and refuses to route when the probe fails rather than handing clients half-open connections.
4. **Streaming adaptation.** Because quick tunnels lack SSE support, the proxy is the place to convert between what clients want (SSE) and what the tunnel can carry (buffered or chunked transfer), decoupling client expectations from tunnel capability.
5. **Header and identity hygiene.** It strips client-identifying headers before forwarding into the home network and adds the upstream auth the home box expects, so nothing inside the house trusts or sees external client details.

## The Named-Tunnel Upgrade Path

1. **Named tunnels remove ephemerality for free.** A remotely-managed tunnel (create in dashboard or `cloudflared tunnel create`) gives a stable hostname on your own zone, works behind CGNAT identically, and the free tier allows dozens of tunnels — the standard homelab recommendation once you own a zone.
2. **Ingress rules replace ad-hoc path logic.** A named tunnel's ingress config maps hostnames and paths to local services (`llm.house.internal:11434` for Ollama, etc.), so the home box can expose several services over one connector.
3. **Zero Trust Access in front of the hostname.** Putting a Cloudflare Access application (service-token policy for machine clients) on the tunnel hostname gives SSO/service-token auth, device posture, and audit logs at the edge — an alternative to the VPS key check for human-facing endpoints.
4. **`cloudflared access` for private origin fetches.** From any machine, `cloudflared access curl --service-token-id ... https://llm.zone.tld/health` reaches the protected origin without opening it publicly, useful for monitoring boxes outside the home network.
5. **Raw TCP needs WARP routing, not public hostnames.** Public tunnel hostnames proxy HTTP/HTTPS; non-HTTP model-serving protocols require WARP-to-Tunnel private network routes instead — plan for it before assuming any protocol can ride the tunnel.

## Failure Modes We Monitor

1. **Silent URL rotation.** If the home box restarts its tunnel but fails to publish the new URL to the state store, the proxy keeps aiming at a dead hostname; the health probe plus an alert on probe age catches this within a minute.
2. **429 storms from the tunnel itself.** A spike of tunnel-origin 429s means the 200 in-flight quick-tunnel cap is being approached — the proxy treats it as a signal to shed load, not to retry harder.
3. **Connector death looks like everything else.** cloudflared crashing produces the same client symptom (upstream timeout) as the model wedging, so the state store records connector liveness separately from model health to triage correctly.
4. **Config drift between the two surfaces.** The `workers.dev` gateway copy and the custom-route copy can drift; both deploy from the same wrangler config, and the tunnel article's lesson generalizes — one source of truth, two deployment targets, health-checked separately.
