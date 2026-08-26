# load-balancer-health-checks

**Issue:** Configuring load balancer health checks so unhealthy backends are removed without false positives
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Health checks are too aggressive and flap healthy backends out of rotation on brief latency spikes. Or checks are too lenient and keep a half-broken backend serving traffic for minutes after it started failing.

## Pattern / Solution
Tune thresholds to match your application's startup time and SLA, and use application-level health endpoints instead of TCP pings.

**Dedicated health endpoint (Express/Node example):**
```js
// GET /healthz — used by load balancer
// GET /readyz — used by Kubernetes readiness probe
app.get('/healthz', (req, res) => res.json({ status: 'ok' }));

app.get('/readyz', async (req, res) => {
  try {
    await db.query('SELECT 1');
    await redis.ping();
    res.json({ status: 'ready' });
  } catch (err) {
    res.status(503).json({ status: 'unavailable', error: err.message });
  }
});
```

**AWS ALB / NLB (Terraform):**
```hcl
resource "aws_lb_target_group" "app" {
  name     = "app-tg"
  port     = 8080
  protocol = "HTTP"
  vpc_id   = var.vpc_id

  health_check {
    path                = "/healthz"
    interval            = 15      # seconds between checks
    timeout             = 5       # max wait for response
    healthy_threshold   = 2       # consecutive successes to mark healthy
    unhealthy_threshold = 3       # consecutive failures to mark unhealthy
    matcher             = "200"
  }
}
```

**Nginx upstream passive health checks:**
```nginx
upstream backend {
  server 10.0.0.1:8080 max_fails=3 fail_timeout=30s;
  server 10.0.0.2:8080 max_fails=3 fail_timeout=30s;
}
```

**Kubernetes liveness vs readiness:**
```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 10
  failureThreshold: 3   # restart pod after 3 failures

readinessProbe:
  httpGet:
    path: /readyz
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 5
  failureThreshold: 2   # remove from Service endpoints
```

## Gotchas
- Never proxy health check traffic through your main app middleware chain — authentication or rate limiting will cause false failures.
- `initialDelaySeconds` must exceed your app's cold-start time; containers that take 20 s to boot need at least 25 s.
- ALB health checks originate from the load balancer's internal IPs, not from `0.0.0.0`; security groups must allow this.
- A health endpoint that queries the DB synchronously can cascade failures — add a timeout and return 200 degraded rather than 503 when the DB is slow but the app is still serving cached data.

## Related
- `nginx-reverse-proxy-config.md`
- `dns-ttl-strategy.md`
- `prometheus-alertmanager-config.md`
