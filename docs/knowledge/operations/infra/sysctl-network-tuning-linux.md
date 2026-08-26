# sysctl-network-tuning-linux

**Issue:** The Linux kernel's default network parameters are conservative values chosen in the early 2000s, tuned for a desktop with one ethernet card, not for proxy servers, database hosts, or 10 Gbit machines handling tens of thousands of concurrent TCP sessions. Defaults like a 128-entry accept queue, 4 MB maximum socket buffers, and loss-based congestion control cause mysterious production symptoms: connections reset under modest load, throughput stuck at a fraction of link speed on long fat networks, and SYN floods succeeding trivially. Because every distribution and every cloud image ships slightly different defaults, and because wrong sysctl values fail silently until peak load, kernel network tuning needs to be explicit, version-pinned, and managed as configuration, not improvised per host with sysctl -w during an incident.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Connection queue and backlog settings

1. **Raise net.core.somaxconn above the default.** This is the ceiling on each listening socket's accept queue. The traditional default of 128 means a burst of 200 simultaneous connections gets refused before the application is even slow. Set it to 4096 or higher on any load balancer, proxy, or queue consumer, and confirm the application actually requests a matching backlog (NGINX listen backlog, somaxconn in Redis, etc.), since the kernel caps the requested value at this sysctl.

2. **Scale net.ipv4.tcp_max_syn_backlog with half-open connection rate.** This governs the queue of connections that have received a SYN but not completed the handshake. Under high arrival rates or SYN-flood-ish patterns, a small backlog drops handshakes in progress; 8192 is a sane production value on connection-heavy tiers.

3. **Widen net.ipv4.ip_local_port_range for outbound-heavy hosts.** Proxies, mail relays, and API clients making many short outbound connections exhaust ephemeral ports at the default range. Use 10240 to 65535 and enable tcp_tw_reuse so TIME_WAIT sockets to different destinations are recycled safely.

4. **Track drops, not just totals.** Before and after changing queue settings, read netstat -s output for listen queue drops and SYN cookies sent; these counters are the ground truth for whether queue tuning actually helped.

## TCP buffer and autotuning limits

1. **Raise the autotuning ceilings, not the defaults.** Linux autotunes TCP window sizes well, but only up to net.core.rmem_max and net.core.wmem_max, which default far too low for 10 Gbit paths. Set both to 16 MB or more (32 MB on long-fat international routes) so autotuning has headroom; leave the default rmem_default and wmem_default alone since autotuning grows buffers on demand.

2. **Understand the bandwidth-delay product before copying numbers.** A buffer must hold roughly bandwidth times round-trip time in flight; a 10 Gbps link with 40 ms RTT needs about 50 MB of combined window. ESnet's FasterData guidance remains the canonical reference: tune maxima for the pipe, let autotuning find the actual size per connection.

3. **Enable tcp_mtu_probing for path-MTU black holes.** Tunnels, VPN overlays, and some cloud encapsulations shrink effective MTU and produce silent hangs on large packets. tcp_mtu_probing 1 recovers from black-holed segments instead of requiring every path to be fixed.

4. **Do not disable autotuning.** Setting fixed tcp_rmem and tcp_wmem values per connection was 2005-era advice; today it caps both small connections (wasting memory) and big ones (starving throughput).

## Congestion control: BBR in 2025-2026

1. **Prefer BBR for lossy or long-distance paths.** net.ipv4.tcp_congestion_control bbr with net.core.default_qdisc fq models bandwidth and RTT directly instead of inferring congestion from packet loss, which lets flows survive the random loss (wifi, transcontinental links) that cripples CUBIC. Community benchmarks routinely report 5 to 40 percent throughput improvements on lossy paths; on a clean LAN the difference is negligible.

2. **Keep CUBIC for LAN and storage networks.** BBR's advantages evaporate at sub-millisecond RTT and its probing can be less fair to competing CUBIC flows on shared internet links, so many fleets run BBR only on edge and egress tiers.

3. **Require the fq qdisc, not fq_codel, with BBR.** The classic pairing is bbr plus fq; on kernels where fq is unavailable, recent BBR versions tolerate other qdiscs, but fq remains the tested combination and the one documented in kernel sources.

4. **Pin the choice per role in sysctl.d drop-ins.** Write a versioned file under /etc/sysctl.d/ (for example 60-net-tuning.conf) per server role, apply via sysctl --system, and store it in configuration management so kernel upgrades and image rebuilds do not silently revert to defaults.

## File descriptors and connection scale

1. **Raise fs.file-max and the per-service LimitNOFILE together.** Socket exhaustion often looks like network failure. Set the system-wide fs.file-max generously, then set the actual per-process limit in the systemd unit (LimitNOFILE=65536 or higher), because the sysctl alone does not apply to systemd services.

2. **Size net.ipv4.tcp_max_tw_buckets and orphan limits.** On connection-churn servers, TIME_WAIT table overflow produces visible errors; set tcp_max_tw_buckets high enough for the churn rate (rule of thumb: connections per second times 60) rather than the default.

3. **Account for conntrack on filtered hosts.** If nftables stateful rules or a Kubernetes CNI is in play, the net.netfilter.nf_conntrack_max table can overflow independently of every TCP sysctl, dropping new connections; tune it in the same change as the rest of the network stack.

## Change management

1. **Baseline with ss, ip -s link, and nstat before touching values.** Capture retransmit rates, drops, and queue overflows per host role so each change has a before and after; a sysctl change without a measurement is a rumor.

2. **Roll out canary-first with automated rollback.** Apply new network sysctls to one instance per tier, soak under real traffic for at least a day including a peak window, and keep the previous sysctl.d file deployable in one command.

3. **Re-validate after kernel upgrades.** Default values and algorithm behavior shift between kernel versions (somaxconn defaults have already risen in newer kernels), so re-read effective values with sysctl -a after major upgrades instead of assuming the old overrides still matter.
