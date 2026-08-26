# ai-gpu-workload-deployment

**Issue:** Deploying AI/ML inference and training workloads on Kubernetes in 2026 — GPU scheduling, model serving, node pools, and cost control
**Date:** 2026-08-12
**Status:** documented

## Symptom
You containerize an LLM inference server (vLLM, TGI, Ollama) and
deploy it like a normal web service. It gets scheduled on a CPU-only
node, crashes with "CUDA error: no GPU found", or lands on a GPU
node but only uses 5% of the GPU while you pay for 100%. Inference
latency is 30 seconds because the model loads into VRAM on every
cold start.

## Root cause
**GPU workloads are not stateless web services.** They need: (1)
GPU-specific node selectors, (2) enough VRAM for the model weights,
(3) warm pools to avoid multi-minute model loads, (4) autoscaling
based on queue depth, not CPU. Treating them like a CRUD API fails.

**Source:** Kubernetes is the AI runtime backbone for 2026 (CNCF,
Fairwinds). NVIDIA device plugin, Kueue, KServe/MMS are standard.

## The "GPU node pool" pattern

Provision a GPU node pool (separate from CPU nodes) and label it:

```bash
# EKS example — create GPU node group (g5.xlarge = 1x A10G)
aws eks create-nodegroup \
  --cluster-name prod \
  --nodegroup-name gpu-pool \
  --node-type g5.xlarge \
  --desired-capacity 2

# Label and taint the GPU nodes
kubectl label nodes -l nvidia.com/gpu.present=true gpu-node=true
kubectl taint nodes -l nvidia.com/gpu.present=true \
  nvidia.com/gpu=present:NoSchedule   # keep CPU pods off GPU nodes
```

Install the NVIDIA device plugin so K8s can see GPUs:
```bash
kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/main/nvidia-device-plugin.yml
```

Verify GPUs are visible:
```bash
kubectl get nodes -o custom-columns="NAME:.metadata.name,GPU:.status.capacity['nvidia\.com/gpu']"
```

## The "request a GPU" deployment pattern

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: llm-inference
spec:
  replicas: 2
  selector:
    matchLabels: { app: llm-inference }
  template:
    metadata:
      labels: { app: llm-inference }
    spec:
      nodeSelector:
        gpu-node: "true"          # only GPU nodes
      containers:
        - name: vllm
          image: vllm/vllm-openai:latest
          args:
            - --model=mistralai/Mistral-7B-Instruct-v0.3
            - --tensor-parallel-size=1
            - --max-model-len=8192
          resources:
            limits:
              nvidia.com/gpu: 1        # request 1 GPU
              memory: "24Gi"
              cpu: "4"
            requests:
              nvidia.com/gpu: 1
              memory: "16Gi"
              cpu: "2"
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 120   # model load takes 1-5 min
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 300   # don't kill during long loads
```

The `nvidia.com/gpu` resource is what triggers GPU scheduling.

## The "avoid cold starts" warm pool pattern

Model loading takes 1-5 minutes. Scale-to-zero kills UX. Use a
minimum replica floor:

```yaml
spec:
  replicas: 1   # never scale to zero — keep model warm in VRAM
```

Or use KServe with `minReplicas: 1` and scale-to-zero only for
non-critical models with `scaleToZero: true` + a known cold-start
SLA.

## The "autoscale on queue depth" pattern

CPU-based HPA is useless for inference (CPU is idle while the GPU
works). Scale on custom metrics (request queue, GPU utilization):

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: llm-inference-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: llm-inference
  minReplicas: 1
  maxReplicas: 8
  metrics:
    - type: Pods
      pods:
        metric:
          name: vllm_requests_waiting    # custom metric from vLLM
        target:
          type: AverageValue
          averageValue: "2"              # scale up when >2 requests queued per pod
```

Requires Prometheus Adapter or KEDA to expose the custom metric.

## The "cost control" pattern

GPUs are the most expensive resource. Time-bound them:

```yaml
# KEDA ScaledObject — scale down after hours
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: llm-daytime-scaler
spec:
  scaleTargetRef:
    name: llm-inference
  minReplicaCount: 1
  maxReplicaCount: 4
  triggers:
    - type: cron
      metadata:
        timezone: America/New_York
        start: "0 7 * * 1-5"    # weekdays 7am
        end: "0 19 * * 1-5"     # weekdays 7pm
        desiredReplicas: "2"
```

Use spot/preemptible GPU instances for batch training, not
real-time inference.

## Verification
- **GPU allocated:** `kubectl describe pod <pod> | grep nvidia.com/gpu`
  shows `1` in limits
- **Model loaded:** `curl http://<pod>:8000/v1/models` returns the
  model
- **Latency:** `time curl -d '{"prompt":"hello"}' .../v1/completions`
  — first token < 500ms after warmup
- **Cost:** check billing — GPU node group should scale to 0 nodes
  (not just 0 pods) when idle, using Cluster Autoscaler

## Gotchas
- **Model load time breaks probes.** Default `initialDelaySeconds:
  0` kills the pod before the model finishes loading into VRAM. Use
  120-300s, or a startup probe.
- **`nvidia.com/gpu` is integer-only.** You cannot request 0.5 GPUs
  with the default device plugin. For GPU sharing, use NVIDIA
  Multi-Instance GPU (MIG, A100/H100 only) or time-slicing via the
  device plugin config.
- **CPU/memory requests must be set.** If you only set GPU limits,
  the pod may get scheduled on a GPU node with insufficient CPU for
  the tokenizer, causing throttling.
- **Image pull is large.** ML images are 5-15GB. Use a pre-pulled
  image cache (DaemonSet) or ECR/ GAR with pull-through cache.
  First deploy can take 20+ minutes just to pull.
- **Do not use Wasm.** Wasm runtimes cannot access GPU. AI inference
  needs CUDA/ROCm via containers. (See
  `wasm-deployment-spin-to-wasmtime.md`.)
- **Node autoscaler creates GPU nodes slowly.** GPU instances
  (p4d, g5) take 3-10 minutes to provision. Keep a warm pool of 1-2
  nodes; do not rely on rapid scale-up.
- **VRAM fragmentation.** Running multiple models on one GPU without
  MIG causes OOM when the second model loads. Use `--gpu-memory-
  utilization` flags or deploy one model per pod.

## Related
- `kubernetes-horizontal-pod-autoscaler.md`
- `kubernetes-resource-limits.md`
- `kubernetes-namespace-isolation.md`
- `finops-cost-optimization.md`
- `load-testing-before-deploy.md`
- vLLM: https://docs.vllm.ai/
- KServe: https://kserve.github.io/website/
- NVIDIA device plugin: https://github.com/NVIDIA/k8s-device-plugin
