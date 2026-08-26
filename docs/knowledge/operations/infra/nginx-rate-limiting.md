# nginx-rate-limiting

**Issue:** Implementing rate limiting in Nginx to protect APIs from abuse and brute-force attacks
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
APIs receive bursts of requests from a single IP that exhaust backend resources or trigger downstream rate limits. Login and password-reset endpoints are targeted by credential stuffing. Without request throttling at the edge, every request hits the application layer.

## Pattern / Solution
Use `limit_req_zone` (token-bucket) and `limit_conn_zone` (concurrent connection cap) together.

```nginx
# /etc/nginx/nginx.conf  (http block)

# Define zones in the http block — NOT inside server/location
limit_req_zone  $binary_remote_addr zone=api:10m     rate=10r/s;
limit_req_zone  $binary_remote_addr zone=login:10m   rate=5r/m;
limit_conn_zone $binary_remote_addr zone=perip:10m;

# Return 429 instead of 503 for rate-limited requests
limit_req_status  429;
limit_conn_status 429;
```

```nginx
# /etc/nginx/sites-available/app.conf  (server/location block)

location /api/ {
    limit_req  zone=api burst=20 nodelay;
    limit_conn perip 20;
    proxy_pass http://backend;
}

location /api/auth/login {
    # Strict: 5 requests/min, no burst
    limit_req  zone=login burst=3 nodelay;
    proxy_pass http://backend;
}
```

**Custom error response for 429:**
```nginx
error_page 429 /rate_limit.json;
location = /rate_limit.json {
    internal;
    default_type application/json;
    return 429 '{"error":"rate_limit_exceeded","retry_after":60}';
}
```

**Logging rate-limited requests (for monitoring):**
```nginx
log_format rate_limited '$remote_addr - $request - $status - limit_req_status:$limit_req_status';
# Then parse $status == 429 in your log aggregation pipeline
```

**Whitelist trusted IPs (bypass rate limit):**
```nginx
geo $limit {
    default         $binary_remote_addr;
    10.0.0.0/8      "";   # empty key = no zone = no limit
    192.168.0.0/16  "";
}
limit_req_zone $limit zone=api:10m rate=10r/s;
```

## Gotchas
- `burst` allows queuing requests above the rate; without `nodelay`, queued requests are held and add latency rather than being rejected immediately.
- Zone memory: `10m` stores ~160,000 IPv4 states; scale up if you have many unique clients.
- Nginx rate limiting is per-worker process; with 4 workers, actual limit is approximately 4× the configured rate — use `worker_processes 1;` in tests or accept this approximation in production.
- `$binary_remote_addr` uses the direct client IP; if behind a CDN, use `$http_cf_connecting_ip` (Cloudflare) or extract from `X-Forwarded-For` with `set_real_ip_from`.

## Related
- `nginx-reverse-proxy-config.md`
- `load-balancer-health-checks.md`
- `network-security-groups.md`
