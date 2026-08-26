# nginx-tuning-buffers-workers

**Issue:** Default NGINX settings are tuned for a small VPS serving static files, not for a production proxy or API gateway handling thousands of concurrent connections. When traffic grows, teams often blame the upstream application or buy bigger servers, when the actual bottleneck is NGINX itself: too few worker connections, accept queues overflowing into the kernel, request bodies spilling to disk because body buffers are too small, and upstream connections torn down and rebuilt on every request because keepalive to the backend was never enabled. Tuning workers, connections, and buffers is one of the highest-leverage, lowest-cost infrastructure changes available, and unlike application rewrites it can be rolled out and measured in an afternoon.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Worker process and connection sizing

1. **Set worker_processes to auto.** NGINX scales best with one worker per CPU core, and the auto directive derives this from the host's core count. Pin workers to cores with worker_cpu_affinity only when the box is dedicated to NGINX; on shared hosts leave affinity off so the scheduler can dodge noisy neighbors.

2. **Budget worker_connections per protocol mix.** Each proxied client consumes roughly two file descriptors (client side plus upstream side), so max proxied clients is worker_processes times worker_connections divided by two. A common production floor is 4096 connections per worker, verified against the OS file descriptor limit via worker_rlimit_nofile; connections above the ulimit silently fail at accept time.

3. **Raise the kernel accept queue to match.** worker_connections is useless if the kernel backlog is 128. Set net.core.somaxconn (and the listen directive's backlog parameter) to 4096 or higher, otherwise bursts overflow before NGINX ever sees them and clients see connection resets rather than slow responses.

4. **Use epoll and let workers accept independently.** Modern NGINX defaults to epoll on Linux and multi_accept off, which is correct for most proxy workloads. Turn on multi_accept only for static-file serving with bursty arrival patterns; for proxies it can starve later workers by grabbing whole backlog batches.

## Keepalive strategy on both sides

1. **Enable upstream keepalive pools.** Without a keepalive block in the upstream group, NGINX opens a fresh TCP connection to the backend for every request, adding a full handshake (plus TLS handshake if the upstream is HTTPS) to every response. A keepalive 64 pool with proxy_http_version 1.1 and a cleared Connection header cuts backend latency dramatically.

2. **Tune client-side keepalive_timeout deliberately.** The default of 75 seconds holds worker connections open far longer than most browser reuse patterns need; 15 to 30 seconds is usually enough and frees connection slots sooner. Do not set it to 0 to "save resources" on a high-traffic site, because you then pay a handshake on every request.

3. **Cap keepalive_requests per client connection.** Raising the default of 1000 is reasonable for internal API gateways where clients are trusted and long-lived; keep it lower at public edges where per-connection fairness matters more than handshake savings.

4. **Keep TLS session reuse aligned with keepalive.** Enable session caching (ssl_session_cache shared:SSL:10m) so resumed connections after a keepalive drop skip full handshakes; this pairs with keepalive rather than substituting for it.

## Buffer tuning to avoid disk spills

1. **Size client_body_buffer_size to your payload profile.** When a request body exceeds this buffer, NGINX writes it to a temporary file on disk, turning a memory copy into synchronous disk I/O. For JSON APIs with payloads under 64 KB, set client_body_buffer_size 128k so typical requests never touch disk; leave large values only on upload endpoints, not server-wide.

2. **Set proxy_buffers for response capture.** Default proxy_buffers (8 x 4k or 8k) are often too small for large API responses, forcing upstream responses to spill to disk via proxy_max_temp_file_size. A common proxy tier is proxy_buffers 16 16k with proxy_buffer_size 16k to hold typical response headers and bodies in memory.

3. **Turn off buffering where latency beats throughput.** For streaming or server-sent-event endpoints, proxy_buffering off delivers upstream bytes to the client immediately instead of accumulating them; this trades throughput for time-to-first-byte, which is usually the right trade for event streams.

4. **Remember large_client_header_buffers for long URLs and auth headers.** Modern JWT-heavy stacks generate URLs and cookie headers well over the 8k default; 4 x 16k avoids spurious 400 errors from oversized headers, which are notoriously hard to trace back to buffer settings.

## Kernel-level companions

1. **Enable sendfile and tcp_nopush for static content.** sendfile lets NGINX hand file data to the socket without copying through userspace, and tcp_nopush packs response headers with the first file chunk. These only matter for file serving, not proxying, but cost nothing to leave enabled.

2. **Check net.ipv4.ip_local_port_range under heavy upstream fanout.** A proxy making millions of short upstream connections can exhaust ephemeral ports; widen the range and enable tcp_tw_reuse so closed upstream sockets are recycled quickly.

3. **Monitor, then change one variable at a time.** Track connections_accepted versus connections_handled, the accept queue drop counter, and upstream connect time histograms before and after each tuning step. Tuning without baselines produces superstition, not performance.
