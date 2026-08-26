# always-on-local-llm-deployment

**Issue:** The 24/7 chat lane needs an LLM that answers instantly at 3 AM with no human at the desk, but a consumer GPU cannot run the big model around the clock without unacceptable power cost and wear. The working split: a small model runs as `llama-server` under systemd on a cheap always-on box (auto-restart, GPU reclaim on failure), with a KV-based self-heal state store so that when the model wedges, a watchdog restarts the server and the state store recovers conversation context; the small model has a 16k context ceiling, and the desktop big model stays interactive-only and is never part of the always-on lane.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Two-Tier Fleet Economics

1. **Always-on means small.** The chat lane's box runs a small model whose idle power draw is negligible; the big desktop model draws hundreds of watts under load and is powered on only when a human drives it interactively — power cost, heat, and fan wear make 24/7 big-model hosting strictly worse than routing hard requests to an API.
2. **Interactive-only is a routing tier, not an afterthought.** The fleet treats the desktop model as an on-demand resource: requests that need its quality queue until it is awake and acquired, while the always-on lane answers everything else immediately.
3. **Cheap-always-on beats big-and-cold for latency.** Model load from disk into VRAM takes tens of seconds to minutes; an always-loaded small model answers in milliseconds, which is why the 24/7 lane exists at all — community practice confirms the choice between always-on daemons and on-demand (or systemd socket-activated) servers is fundamentally a latency-vs-idle-cost decision.
4. **One model, one job.** The small model serves only chat-lane traffic; batch jobs and tool-heavy workloads go elsewhere, so wedging one workload never starves the interactive lane.

## The systemd Unit That Survives the Night

1. **`Restart=always` plus burst damping.** The unit restarts the server on any exit, but `StartLimitIntervalSec`/`StartLimitBurst` prevent a crash loop from pegging the GPU; standard practice for llama-server daemons is exactly this shape (`Restart=always`, `WantedBy=multi-user.target`).
2. **GPU reclaim on every restart.** Because a crashed server can leave VRAM allocated, the unit's restart path runs `nvidia-smi --gpu-reset` (or kills stale compute processes) before ExecStart, so the model never fails to reload because its own ghost still holds memory.
3. **Sandbox lightly, not maximally.** The unit applies baseline hardening (`NoNewPrivileges`, `ProtectSystem`, `DynamicUser` where the model cache permits) but GPU services need device access and large mapped model files, so aggressive `PrivateDevices`/`MemoryDenyWriteExecute` style lockdown breaks them — apply what survives a real inference test, and see `infra/systemd-service-hardening` for the general checklist.
4. **Pin the launch flags in the unit.** Context size (`-c 16384`), parallel slots, cache type, and the model path live in `ExecStart`, so every restart produces an identically configured server instead of depending on shell history or a tmux session someone forgot.
5. **Mind the cache directory.** llama-server under systemd has a known failure mode around its cache dir (LLAMA_CACHE, ggml-org/llama.cpp#20952) — give the unit an explicit, writable cache/model state path or it will die at load time in ways a manual shell run never showed.

## Watchdog and KV Self-Heal

1. **The model can wedge without dying.** The process stays up, health endpoint still answers TCP, but completions hang forever — VRAM fragmentation, a stuck CUDA context, or a poisoned prompt loop; process-level restart alone cannot see this, so the watchdog probes an actual tiny completion, not `/health`.
2. **`WatchdogSec` needs `sd_notify`, and llama-server does not send it.** systemd's built-in watchdog only works for services that call `sd_notify(0, "WATCHDOG=1")`; llama-server does not, so heartbeats come from an external watchdog process (cron/timer) that runs the probe completion and escalates to `systemctl restart` on repeated failure.
3. **State lives outside the server.** Conversation state, active session keys, and the last-N turns are written to a KV store as the lane runs; the server itself is stateless and disposable, which is what makes "restart it whenever it looks wrong" a safe first response.
4. **Recovery is reconstruct, not resume.** After a restart, the lane rebuilds context by replaying the stored turns as a single priming request — there is no attempt to snapshot and restore KV cache memory itself, which would be fragile across restarts and model versions.
5. **Restart budget caps the loop.** The self-heal path is rate-limited (max N restarts per hour before it pages a human instead of restarting again), because a model that wedges every five minutes is a configuration problem, not something restarts will fix.
6. **Memory creep is the top wedge cause.** Long-lived inference processes are widely reported to grow resident memory over days; the watchdog treats a slow latency regression across probes as an early signal, and a scheduled off-peak restart drains accumulated state before users notice.

## The 16k Context Ceiling

1. **The ceiling is a routing input.** With 16k tokens for the small model, the lane tracks live token usage per session and escalates to summarization or to the big-model tier before the window fills, instead of failing mid-conversation with a context-length error.
2. **Rolling summary keeps sessions unbounded.** When stored history approaches the budget, older turns are folded into a compact summary in the KV store and the reconstructed context becomes summary + recent turns — cheap, predictable, and lossy only where it matters least.
3. **Tool outputs are the silent budget eaters.** A single large tool response can consume a quarter of the window; the lane truncates oversized tool outputs (or folds them into the rolling summary) before they enter context, rather than letting one webhook payload evict the whole conversation.
4. **Size the ceiling in the unit, not the request.** The `-c 16384` launch flag is the enforcement point — requests asking for more context than the server was started with fail at the server, so the lane's budget logic must know the unit's configured number exactly.

## Ollama vs llama-server as the Daemon

1. **llama-server gives a predictable footprint.** No hidden model-swap or keep-alive semantics: what you load is what runs, memory behavior is stable, and the surface is the OpenAI-compatible API the gateway already speaks — the reason the 24/7 lane chose it over Ollama despite Ollama's nicer ops story.
2. **Ollama's conveniences are real but opinionated.** Built-in daemon, model pull/load lifecycle, and `keep_alive` unloading make Ollama the easier single-box default, but background unloading is exactly what an always-on lane does not want, and its concurrency behavior under parallel load is weaker in community comparisons.
3. **One process, one job beats one daemon, many models.** Multi-model hosts (Ollama serving several GGUFs, or `llama-swap` under systemd) are the right tool when models share a GPU part-time; the always-on lane avoids that entirely — dedicated box, dedicated model, no contention.
4. **Whatever the engine, systemd owns it.** Both Ollama and llama-server end up as `Restart=always` units with explicit resource limits; the engine choice changes the flags, not the operational pattern of probe, restart, reconstruct.
