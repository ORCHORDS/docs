# containers-cold-start-gpu-ai-inference

Running AI inference (LLMs, image generation, embeddings) inside Cloudflare
Containers with GPU support. Covers the #1 pain point teams hit in 2026:
**cold-start latency on GPU containers**, plus cost control and model loading.

## Symptom

Your AI inference endpoint works perfectly under load, but the **first request
after idle takes 15-45 seconds** — sometimes timing out. Users see `524 Timeout`
or the client gives up before the model finishes loading into GPU memory.

```text
POST /infer → 524 after 100s (container cold-starting, model not in VRAM)
POST /infer → 200 in 800ms (warm: model already loaded)
```

The pattern: bursty traffic = fine; sparse traffic = unusable.

## Root Cause

Cloudflare Containers spin down after idle. When a new request arrives:

1. Container image is pulled (cached after first pull, ~2-5s)
2. Container starts, runtime boots (~1-3s)
3. **Model weights load from disk/registry into GPU VRAM (~10-30s for 7B+ models)** ← the killer
4. Inference engine initializes CUDA/tensor contexts (~2-5s)
5. Request is finally processed

Steps 1-2 and 4 are fast. Step 3 dominates because model weights (4-15 GB)
must transfer into VRAM every cold start.

## Solution: Keep models warm

### Option A: Minimum-instances (always-on) — simplest

```toml
# wrangler.toml
[[containers]]
name = "llama-inference"
image = "./Dockerfile"
max_instances = 4
min_instances = 1          # keep 1 always warm (billed continuously)
```

Pros: zero cold start after first deploy.
Cons: you pay 24/7 for that instance even with zero traffic.

### Option B: Scheduled warm-up via cron Worker

```typescript
// warmup-worker.ts — runs every 4 minutes
export default {
  async scheduled(event: ScheduledEvent, ctx: ExecutionContext) {
    // Hit your inference endpoint with a tiny dummy request
    // to keep the container above the idle threshold
    await fetch("https://llama-inference.<account>.containers.cloudflare.com/warmup", {
      method: "POST",
      body: JSON.stringify({ prompt: "ping", max_tokens: 1 }),
    });
  },
};
```

```toml
# wrangler.toml for the warmup worker
name = "container-warmup"
main = "warmup-worker.ts"

[triggers]
crons = ["*/4 * * * *"]   # every 4 minutes
```

**Tune the interval**: Cloudflare's default idle timeout is ~5 minutes. Set
cron to 4 minutes to be safe. Test your actual threshold — it can vary.

### Option C: Use Workers AI for the cold path, Container for the hot path

Route based on latency budget:

```typescript
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const latencyBudget = parseInt(req.headers.get("X-Latency-Budget") || "5000");

    if (latencyBudget < 5000) {
      // Fast path: Workers AI (warm, shared infra, smaller models)
      const result = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
        prompt: await req.text(),
      });
      return Response.json({ result, source: "workers-ai" });
    }

    // Slow path: your GPU container (larger model, your fine-tune)
    const result = await fetch(`https://llama-70b.<account>.containers.cloudflare.com/infer`, {
      method: "POST",
      body: await req.text(),
    });
    return new Response(result.body, { headers: { "X-Source": "container-gpu" } });
  },
};
```

## Reducing model load time (when cold starts are unavoidable)

### 1. Pre-download weights into the image

```dockerfile
# Dockerfile — bake model into image, don't fetch at runtime
FROM python:3.12-slim

# Install inference engine
RUN pip install vllm

# Pre-download model weights at BUILD time (not runtime!)
RUN mkdir -p /models && \
    huggingface-cli download meta-llama/Llama-3.1-8B-Instruct \
    --local-dir /models/llama-8b

# Image is now 8GB+ but cold start skips the download step entirely
ENV MODEL_PATH=/models/llama-8b
CMD ["python", "-m", "vllm.entrypoints.openai.api_server", "--model", "/models/llama-8b"]
```

### 2. Use quantized models (GGUF/AWQ)

```dockerfile
# 4-bit quantized model: 4GB instead of 15GB → 4x faster VRAM load
ENV MODEL_PATH=/models/llama-8b-q4_k_m.gguf
```

A Q4 quantized 8B model loads in ~3s vs ~12s for FP16.

### 3. Use a memory-mapped volume

```toml
[[containers]]
name = "llama-inference"
image = "./Dockerfile"

[[containers.volumes]]
name = "model-cache"
mount_path = "/models"
```

## Gotchas

- **GPU billing is per-second, not per-request.** A `min_instances = 1` GPU
  container costs ~$0.50-1.50/hour depending on GPU tier — that's
  $360-$1,080/month minimum. Budget before you set it.
- **Container image size affects first-ever cold start.** A 15GB image (with
  baked-in model) takes longer to pull the first time but skips runtime
  download. Trade-off: faster steady-state cold starts vs. slower first deploy.
- **`min_instances` is per-region by default.** If you need global coverage
  with min_instances, you multiply cost by region count. Usually one region
  with smart routing is enough.
- **Workers AI vs Containers AI is not either/or.** Workers AI has no cold
  starts but limits you to Cloudflare's catalog. Containers let you run
  anything but you own the cold-start problem. Use both.
- **Health check must validate model-loaded state, not just port-open.** If
  your health check returns 200 before the model is in VRAM, Cloudflare will
  route traffic to a container that's "up" but will still take 15s on first
  inference. Make `/health` return 503 until `model_loaded == true`.
- **Cold start times are NOT in Cloudflare's metrics dashboard by default.**
  Add custom logging: log `container_boot_ms` and `model_load_ms` as
  Analytics Engine data points so you can actually see the problem.
- **GPU containers are NOT available on the free plan.** Workers Paid ($5/mo)
  is the minimum, and GPU containers have separate pricing — check the
  containers pricing page, not the Workers pricing page.
- **Don't put your inference Worker and GPU container in the same wrangler.toml
  unless you understand the deploy coupling.** Deploying the Worker redeploys
  the container. Use separate projects for independent iteration.

## Reference architecture

```text
User → Workers (edge, <50ms) → GPU Container (regional, AI inference)
                ↓ (cold path, small models)
           Workers AI (shared infra)
```

- Worker handles auth, rate limiting, request validation (fast, cheap, global)
- Worker routes to container for large/custom models
- Worker falls back to Workers AI for small models or when container is cold
