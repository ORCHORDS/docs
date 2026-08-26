# fetch-priority-hints

**Issue:** Browsers assign every network request a priority using heuristics based on resource type and discovery order, and those heuristics are frequently wrong for the resources that actually matter. The most common and costly case is the LCP hero image: an img tag discovered late in the markup, or painted via a CSS background that the preload scanner cannot see at all, starts downloading at a low priority behind scripts and stylesheets it does not need to wait for. The fetchpriority attribute (the shipped part of the old Priority Hints proposal) lets developers raise or lower the priority of individual fetches, and it is now supported across all major browsers since Firefox 132 shipped it in late 2024. Used precisely, it removes seconds of load delay from LCP images; used carelessly, it starves everything else on the page.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How browsers prioritize without hints

1. **The preload scanner walks ahead of the parser.** Before the HTML parser finishes building the DOM, a secondary scanner skims the raw markup for img, script, and link tags to start fetches early. Resources only referenced from CSS or JavaScript are invisible to this scanner, which is why background-image heroes and JS-injected images are systematically deprioritized.

2. **Default priorities are type-based, not importance-based.** CSS starts high because it blocks rendering, scripts start high when parser-blocking, and images start low-to-medium because the browser assumes most are below the fold. An above-the-fold image therefore competes with dozens of unimportant ones purely by category.

3. **Late discovery demotes even critical resources.** When the LCP image is discovered after stylesheets and scripts have queued, it lands behind them in the network queue regardless of how visually urgent it is. WebPageTest and Chrome DevTools show this as high "load delay" — time the request could have been in flight but was not.

4. **Layout-responsive images add a discovery penalty.** For srcset images the browser must compute layout before selecting a candidate, and for client-rendered SPAs the image URL may not exist until a framework finishes hydrating, compounding the late-discovery problem that fetchpriority is meant to correct.

## Applying fetchpriority correctly

1. **Mark exactly one image fetchpriority="high".** Annotate the probable LCP element — usually the hero or first in-view image — with fetchpriority="high". web.dev guidance is explicit that this is the primary use case, and the effect is largest when the image is otherwise discovered late.

2. **Preload background and JS-discovered heroes.** If the LCP element is a CSS background image or rendered client-side, add a link rel="preload" as="image" with fetchpriority="high" in the head. The preload forces early discovery; the priority attribute stops it queueing behind lower-value fetches.

3. **Match preload attributes to the img exactly.** When preloading a responsive image, repeat the srcset and sizes values as imagesrcset and imagesizes on the link. A mismatch causes a double download (two different candidates fetched) or a wasted low-priority fetch, both of which make LCP worse than doing nothing.

4. **Demote the demotable.** fetchpriority="low" on below-the-fold carousels, third-party pixel images, and prefetch-style fetches frees bandwidth and connection slots for the LCP resource. Demotion is often higher leverage than promotion because it does not dilute the high-priority signal.

5. **Never lazy-load the LCP image.** loading="lazy" on an above-the-fold image defeats every priority signal — the browser deliberately delays it until layout and intersection are known. Remove lazy from the hero before adding fetchpriority; the two instructions contradict each other.

## Pitfalls and anti-patterns

1. **Priority inflation.** Marking many images or scripts high does not make everything fast; it restores the contention the attribute exists to solve, just at a higher baseline. Treat the high value as a budget of one or two fetches per page.

2. **Ignoring the priority chain.** A high-priority image still waits on a blocking stylesheet if the render path requires it, and on the TLS connection if the origin is cold. fetchpriority reorders the queue; it does not remove render-blocking or connection-setup dependencies that need their own fixes.

3. **Server-side priority mismatch.** Raising client priority does not help when an origin server or CDN serializes responses slowly. HTTP/2 and HTTP/3 stream scheduling on the server side must also respect urgency, which is where the RFC 9218 Extensible Priorities header matters for streamed responses.

4. **Shipping hints for pages that never measure.** Templates that blanket-add fetchpriority="high" to a header image across all routes end up promoting non-LCP images on some pages. Derive the hint from the actual per-route LCP element, ideally from field (RUM) data, not from a layout assumption.

## Measuring the effect

1. **Read the LCP phase breakdown.** In Chrome DevTools Performance insights or web-vitals attribution data, split LCP into load delay, load time, render delay. fetchpriority primarily shrinks load delay; if load time dominates, the fix is image size, format, or CDN instead.

2. **Verify priority in the Network panel.** DevTools shows the computed priority for every request. Confirm the hero actually moved from Low/Medium to High after the change, and that nothing critical moved down as a side effect.

3. **Use the Priority column in testing tools.** WebPageTest and Lighthouse flag "LCP image loaded with low priority" — a direct audit for this exact mistake. Run it on mobile profiles, where connection contention is most punishing and the win is largest.

4. **Confirm in field data before declaring victory.** Lab improvements in load delay should translate to CrUX or RUM LCP deltas over a rollout window. If the p75 does not move, the image was probably not priority-bound, and further effort belongs in compression or discovery-order fixes instead.
