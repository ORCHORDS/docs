# nginx-reverse-proxy-config

**Issue:** Production-ready Nginx reverse proxy configuration with TLS, headers, and upstream buffering
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Default Nginx configs lack security headers, have incorrect timeout values for WebSocket or streaming endpoints, leak upstream server information, and do not handle large request bodies or slow clients safely.

## Pattern / Solution
A production baseline for proxying a Node/Python/Go backend.

```nginx
# /etc/nginx/sites-available/app.conf

upstream backend {
    server 127.0.0.1:8080 max_fails=3 fail_timeout=30s;
    keepalive 32;
}

server {
    listen 80;
    server_name example.com www.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name example.com www.example.com;

    ssl_certificate     /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache   shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_stapling        on;
    ssl_stapling_verify on;

    # Security headers
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Hide server info
    server_tokens off;

    # Request limits
    client_max_body_size 10m;
    client_body_timeout  30s;

    location / {
        proxy_pass         http://backend;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_set_header   Connection        "";  # required for keepalive

        proxy_connect_timeout 5s;
        proxy_read_timeout    60s;
        proxy_send_timeout    60s;

        # Buffer tuning
        proxy_buffering    on;
        proxy_buffer_size  4k;
        proxy_buffers      8 4k;
    }

    # WebSocket endpoint
    location /ws {
        proxy_pass         http://backend;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade    $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_read_timeout 3600s;
    }

    # Static files — serve directly, bypass backend
    location /static/ {
        root /var/www/app;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

## Gotchas
- `proxy_set_header Connection ""` clears the hop-by-hop Connection header needed for upstream keepalive — without it, connections are closed after each request.
- `ssl_stapling on` requires `resolver` directive if Nginx resolves OCSP responder hostnames; add `resolver 8.8.8.8 valid=300s;` at the `http` block level.
- `add_header` in a location block does NOT inherit headers from the server block in older Nginx; repeat them or use `always` and move to `http` block.
- Streaming/SSE endpoints need `proxy_buffering off;` and `X-Accel-Buffering: no` to avoid response being held until buffer fills.

## Related
- `nginx-rate-limiting.md`
- `ssl-tls-certificate-management.md`
- `load-balancer-health-checks.md`
