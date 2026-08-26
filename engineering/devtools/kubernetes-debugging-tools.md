# Kubernetes Debugging Tools

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

A pod is in CrashLoopBackOff, OOMKilled, or stuck in Pending, and you
cannot determine why. Your production containers use distroless images
with no shell, so `kubectl exec` is useless. Debugging requires SSH-ing
into nodes, grepping scattered logs, and guessing at resource states
because you have no interactive tooling.

## Context

Kubernetes debugging has matured significantly by 2026. Ephemeral debug
containers (stable since Kubernetes 1.25) allow attaching fully-tooled
containers to running pods without restarts. Combined with tools like k9s,
stern, and kubectl plugins, engineers can debug cluster issues without
leaving the terminal or modifying production workloads.

## Core tools

### kubectl debug (native)

Attaches an ephemeral debug container to a running pod, sharing its
namespaces (PID, network, IPC) without restarting the workload. Works
even with distroless images that have no shell.

```bash
# Attach a debug container to a running pod
kubectl debug -it pod/api-server-7d4b \
  --image=nicolaka/netshoot \
  --target=api-server \
  -- /bin/bash

# Debug a node directly
kubectl debug node/worker-01 -it --image=ubuntu

# Create a copy of a pod with a debug container
kubectl debug pod/api-server-7d4b -it \
  --copy-to=api-debug \
  --container=debug \
  --image=busybox
```

### k9s (terminal UI)

Real-time terminal UI for Kubernetes cluster management. Provides Vim-like
navigation, pod logs, shell access, resource editing, and multi-cluster
support without typing kubectl commands.

| Shortcut | Action |
|---|---|
| `:pods` | List pods |
| `:deploy` | List deployments |
| `:events` | Show cluster events |
| `l` | View logs |
| `s` | Shell into container |
| `d` | Describe resource |
| `ctrl-d` | Delete resource |
| `:xray deploy` | X-ray view of a deployment (pods, containers, volumes) |

### stern (multi-pod log tailing)

Tails logs from multiple pods and containers simultaneously with color-
coded output. Supports regex matching on pod names.

```bash
# Tail all pods matching a pattern
stern "api-server.*" --namespace production

# Tail with timestamps and specific container
stern "worker-*" -c main --timestamps --since 5m

# Tail across all namespaces
stern "payment" --all-namespaces
```

### kubectl plugins (krew)

Krew is the plugin manager for kubectl. Essential plugins:

| Plugin | Purpose |
|---|---|
| `kubectl neat` | Clean up verbose YAML output (remove managed fields) |
| `kubectl tree` | Show resource ownership hierarchy |
| `kubectl images` | List container images running in the cluster |
| `kubectl resource-capacity` | Show node resource usage vs. capacity |
| `kubectl who-can` | RBAC authorization check |
| `kubectl sniff` | Capture network traffic from a pod |

```bash
# Install krew and plugins
kubectl krew install neat tree images resource-capacity
```

## Debugging common scenarios

### CrashLoopBackOff

```bash
# 1. Check events
kubectl describe pod <name> | grep -A 20 Events

# 2. Check previous container logs
kubectl logs <pod> --previous

# 3. Override entrypoint to keep pod alive for debugging
kubectl debug <pod> -it --copy-to=debug-pod \
  --container=app -- sleep infinity
```

### OOMKilled

```bash
# 1. Confirm OOM in events
kubectl describe pod <name> | grep OOMKilled

# 2. Check resource limits vs. actual usage
kubectl top pod <name>

# 3. Check memory patterns over time
kubectl debug -it <pod> --image=nicolaka/netshoot \
  --target=app -- cat /sys/fs/cgroup/memory.current
```

### Pending pod (unschedulable)

```bash
# 1. Check scheduler events
kubectl describe pod <name> | grep -A 5 Events

# 2. Check node resources
kubectl resource-capacity --sort cpu.util

# 3. Check taints and tolerations
kubectl get nodes -o custom-columns=\
  NAME:.metadata.name,TAINTS:.spec.taints
```

## Anti-patterns

- **SSH into nodes** — kubectl debug node and ephemeral containers
  eliminate the need for node SSH access. Granting SSH to production
  nodes is a security risk.
- **Adding debug tools to production images** — installing curl, nslookup,
  and strace in production containers increases image size and attack
  surface. Use ephemeral containers instead.
- **`kubectl exec` as the only debug tool** — exec fails on distroless
  containers and requires a running shell. kubectl debug works regardless
  of the base image.
- **Manual log grepping** — tailing individual pod logs with `kubectl logs`
  does not scale beyond a few pods. Use stern for multi-pod tailing and a
  log aggregation pipeline for structured search.

## Gotchas

- **Ephemeral containers cannot be removed** — once attached, an
  ephemeral container stays until the pod is deleted. This is by design
  but means you should not leave long-running debug containers in
  production pods.
- **k9s requires RBAC** — k9s needs read access to the resources you
  want to view. In restricted clusters, you may need a dedicated
  ClusterRole.
- **stern memory usage** — tailing logs from many pods simultaneously
  consumes memory proportional to the log volume. Use `--since` to limit
  the time window.
- **Network namespace sharing** — ephemeral debug containers share the
  pod's network namespace, so they can see all network traffic. This is
  useful for debugging but be aware of the security implications.

## Verification

- kubectl debug is available in your cluster (Kubernetes 1.25+).
- k9s is installed and configured for all target clusters.
- stern is available for multi-pod log tailing.
- Krew plugin manager is installed with essential plugins.
- Debug workflow documentation exists for the top 5 failure modes.
- RBAC allows engineering teams to use debug tools without node SSH.

## Related

- `documentation/categories/monitoring/log-aggregation-architecture-patterns.md`
- `documentation/categories/monitoring/golden-signals-monitoring.md`
- `documentation/categories/infra/kubernetes-resource-management.md`

## Source URLs (verified 2026-08-16)

- kubectl debug guide — https://oneuptime.com/blog/post/2026-02-20-kubernetes-kubectl-debug-guide/view
- Top Kubernetes debugging tools 2026 — https://kubezilla.io/top-10-kubernetes-debugging-tools-every-devops-engineer-needs-in-2026/
- Ephemeral containers — https://kubernetes.io/docs/concepts/workloads/pods/ephemeral-containers/
- k9s — https://k9scli.io/
- stern — https://github.com/stern/stern
