# service-discovery-consul

**Issue:** Service discovery and health-check-based routing with HashiCorp Consul
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Services using hardcoded IPs or DNS that don't reflect health. New instances not picked up automatically. Load balancer configuration lag on deploys.

## Pattern / Solution
Service registration (via Consul agent on each host):
```hcl
# /etc/consul.d/api.hcl
service {
  name = "api"
  port = 8080
  tags = ["v2", "primary"]

  check {
    name     = "HTTP health"
    http     = "http://localhost:8080/health"
    interval = "10s"
    timeout  = "3s"
    deregister_critical_service_after = "30s"
  }
}
```

DNS-based discovery (built into Consul):
```bash
# Any service can resolve healthy instances via DNS
dig @127.0.0.1 -p 8600 api.service.consul SRV
# Returns: IP:port of all healthy api instances
```

Consul Template — render configs with live service addresses:
```
# nginx.ctmpl
upstream api {
  {{range service "api"}}
  server {{.Address}}:{{.Port}};
  {{end}}
}
```

```bash
consul-template -template "nginx.ctmpl:/etc/nginx/upstream.conf:nginx -s reload"
```

Service mesh with Consul Connect:
```hcl
service {
  name = "frontend"
  connect {
    sidecar_service {
      proxy {
        upstreams = [{
          destination_name = "api"
          local_bind_port  = 9090
        }]
      }
    }
  }
}
```

## Gotchas
- Consul raft requires 3 or 5 server nodes for quorum — never run 2 servers
- Health check deregistration delay prevents flapping on transient failures — tune to > restart time
- DNS TTL for Consul is 0 by default — clients must re-query on each request (use caching DNS resolver to buffer)
- ACL tokens required in production — unauthenticated Consul is a privilege escalation risk

## Related
- `load-balancer-health-checks.md`
- `nginx-reverse-proxy-config.md`
- `linkerd-vs-istio-2026.md`
