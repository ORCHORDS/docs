# streaming-ssr-performance

**Issue:** Classic server-side rendering buffers the entire HTML before sending anything: the browser stays blank for the full duration of the slowest data fetch plus render, so TTFB on SSR routes commonly sits at 100-300 ms and far worse when one upstream is slow. Streaming SSR inverts this — the server flushes the app shell immediately, then streams Suspense-wrapped sections as their data resolves, letting the browser discover CSS, fonts, and images while the backend is still working. Case studies report TTFB reductions around 60% and, combined with selective hydration, client-bundle reductions of 30-60%. The technique is now table stakes in React 18+/Next.js/TanStack Start, but it also introduces new failure modes: misleading TTFB numbers, hydration waterfalls, and head/SEO trade-offs that this article covers.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Shell-first streaming

1. **Flush the shell immediately.** Everything that does not depend on per-request data — navigation, layout, skeleton containers — should be committed on the first chunk. The browser starts fetching stylesheets and the hydration bundle during the exact window the server is otherwise blocking on databases and APIs.
2. **Wrap slow data in Suspense boundaries.** Each boundary is a streaming unit: the server emits a fallback in the shell, then an inline template with the real content when its data resolves, and the client swaps it in. Place boundaries around genuinely slow or low-priority regions (comments, recommendations, below-fold panels), not around the whole page, which serializes instead of parallelizes.
3. **Do not let one slow query hold the shell.** Any data dependency above the first Suspense boundary is still a full-buffering tax; audit the critical path and push anything non-essential below a boundary. Target shell flush in tens of milliseconds, with data sections arriving later.
4. **Errors need boundaries too.** A rejected promise inside a streamed section must resolve to an error UI, not a hanging connection; define error boundaries so one bad section degrades alone.

## Selective and partial hydration

1. **Hydrate only what is interactive.** Static markup (prose, marketing blocks, lists) does not need JavaScript attached; islands-style or partial-hydration approaches report 30-60% bundle reductions and materially faster interactivity on low-end devices, which is where INP pain concentrates.
2. **Load React first.** Official React 18 guidance: keep a minimal entry that loads React and the hydration runtime as early as possible, separate from heavier app code, so selective hydration can start the moment the user interacts instead of waiting for the whole graph.
3. **Selective hydration prioritizes interaction.** When a user clicks inside a not-yet-hydrated Suspense section, React prioritizes hydrating that boundary, capping the perceived latency of eager users; ensure boundaries align with interaction regions so this scheduling can work.
4. **Avoid hydration waterfalls.** Client components that fetch their own data on mount recreate the server waterfall in the browser; data should arrive with the stream (server-rendered props or serialized caches), with client fetching reserved for genuinely post-load refresh.

## Measurement pitfalls

1. **TTFB lies under streaming.** A fast first chunk is not a loaded page; streaming makes TTFB look artificially low while the meaningful content may arrive seconds later. Track LCP element timing and a custom "last boundary resolved" metric alongside TTFB, exactly the caution patterns.dev raises.
2. **Instrument per-boundary timings.** Server-timing headers per section (data start/stop, flush time) plus client-side marks when each Suspense fallback swaps for content expose which section is the tail; the slowest boundary, not the shell, is usually the optimization target.
3. **Watch for render-blocking chains.** The streamed shell still references CSS that blocks first paint; early-hints or inlined critical CSS keep the shell's advantage from being eaten by stylesheet discovery.
4. **Compare against perceived metrics.** A/B streaming against buffered SSR with field data (LCP, INP) rather than lab TTFB alone — especially on throttled mobile profiles, where early paint of skeletons plus progressive content reliably beats late complete paint.

## Head, SEO, and correctness trade-offs

1. **Metadata arrives late.** Title, meta description, and Open Graph tags live in head, but streamed content sections resolve after the initial flush; frameworks solve this with late head injection, though raw document.title swaps after crawlers snapshot can cost social-card correctness — validate with a fetch-and-render SEO audit (the unhead streaming research documents these trade-offs).
2. **Crawlers mostly cope, verify anyway.** Googlebot renders JS and generally handles streamed documents, but verify with the URL inspection tool that titles and canonicals are present post-render, and consider keeping critical SEO metadata out of Suspense boundaries entirely.
3. **Skeletons and CLS.** Fallbacks must reserve the final content's dimensions; mismatched skeleton heights swap with layout shift, converting a TTFB win into a CLS loss that field data will faithfully report.
4. **Hydration mismatches.** Time-dependent or random content rendered on the server then re-rendered on the client produces mismatch warnings and re-renders; stream stable markup and move volatile values to effects.

## Operations

1. **Ensure your platform streams.** Compression layers, proxies, and frameworks can buffer responses and silently reintroduce full-buffering; curl with a flushed-chunk check (or watching bytes arrive incrementally) in production is the only trustworthy verification.
2. **Timeouts beat hangs.** Boundaries whose data sources hang should fall back after a deadline (for example, 5-10 s) and stream a retry-able state; a client left staring at a skeleton forever is worse than the buffered page you replaced.
3. **Load-shed by section.** Because sections are independent, degraded mode can drop optional boundaries under load (recommendations, activity) while keeping the core page fast — a resilience property buffered SSR cannot offer.
