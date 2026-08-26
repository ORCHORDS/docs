# docker-network-modes

**Issue:** Choosing and configuring Docker network modes for security and performance
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Default bridge networking exposes containers to each other unnecessarily. Host networking bypasses isolation. Understanding network modes is essential for secure multi-container deployments.

## Pattern / Solution
Network mode comparison:
| Mode | Use case | Isolation |
|------|----------|-----------|
| bridge (default) | Multi-container dev | Moderate |
| host | High-perf, single host | None |
| none | Fully isolated sidecars | Maximum |
| overlay | Docker Swarm multi-host | Good |
| macvlan | Legacy app, needs MAC addr | Good |

Custom bridge with DNS:
```bash
docker network create \
  --driver bridge \
  --subnet 172.20.0.0/16 \
  --ip-range 172.20.240.0/20 \
  --gateway 172.20.0.1 \
  --label project=myapp \
  myapp-net
```

Isolating frontend from backend:
```yaml
services:
  frontend:
    networks: [public, internal]
  api:
    networks: [internal]
  db:
    networks: [internal]

networks:
  public:
    driver: bridge
  internal:
    driver: bridge
    internal: true   # no routing to host or internet
```

Inter-container DNS resolution:
```bash
# Containers on the same user-defined network resolve by service name
docker exec frontend curl http://api:8080/health
```

## Gotchas
- Default bridge network does NOT support DNS resolution by container name; user-defined networks do
- `--network host` on Linux gives container access to all host interfaces and bypasses all iptables rules
- Docker creates a new iptables chain per network; many networks + many containers can exhaust iptables capacity
- `internal: true` networks cannot pull images from the internet — pre-pull or use a private registry
- Overlay networks in Swarm require specific ports open between hosts: TCP 2377, TCP/UDP 7946, UDP 4789

## Related
- `docker-compose-production.md`
- `docker-security-scanning.md`
- `kubernetes-network-policies.md`
