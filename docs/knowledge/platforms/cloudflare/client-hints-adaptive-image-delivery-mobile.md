# Client Hints and Adaptive Image Delivery on Cloudflare

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

example project (example.com) feeds are media-heavy: R2-hosted user uploads
transformed via Cloudflare Images dominate mobile data usage. iOS
Safari users report slower feeds and higher data use than Android
Chrome users viewing identical content. Transformation URLs use
`width=auto`, and Chrome DevTools mobile emulation looks correct —
but real iPhones receive 1200px-wide "desktop" renditions on a
390px viewport. Nothing in the Next.js static export or the Worker
API is wrong; the disparity is caused by which browsers send client
hints and which silently fall back to user-agent detection.

## Context

Cloudflare Image Transformations support `width=auto`: the edge
picks an image width from information the browser sends. Browsers
that support client hints (Chromium family: Chrome, Edge, Opera,
Samsung Internet) send the viewport width in a request header
(`Sec-CH-Viewport-Width`); Cloudflare snaps it to a breakpoint and
serves that size. Safari (macOS and iOS, all versions) and Firefox
have never implemented these hints, so those users fall into a
coarse user-agent-detection fallback. Because iOS Safari is a huge
share of mobile traffic, an `auto`-only strategy quietly degrades
for the exact audience where image bytes matter most. The robust
cross-browser mechanism remains `srcset`/`sizes`, with client hints
as a Chromium-side enhancement.

## How width=auto resolves a width

```
Request for /cdn-cgi/image/width=auto,format=auto/media/abc.jpg

            ┌─────────────────────────────────┐
            │ Sec-CH-Viewport-Width present?  │
            └──────┬───────────────────┬──────┘
              yes  │                   │  no (Safari, Firefox)
                   ▼                   ▼
        snap up to breakpoint    user-agent sniffing
        (smallest >= viewport)   mobile UA  → 768px
                                 desktop UA → 1200px
        default breakpoints:
        320 / 768 / 960 / 1200
        above 1200 → serve 1200
```

- Breakpoint snapping is deliberate: bounding the set of generated
  widths bounds cache fragmentation and billable transformations
  (each unique width is a separate billable transformation).
- Customize breakpoints with semicolon-separated positive integers:
  `width=auto,wbreakpoints=320;768;960;1920`.
- Override the UA-fallback widths with `wmobile` and `wdesktop`:
  `width=auto,wmobile=480,wdesktop=1280`.
- `dpr` scales output for screen density (default 1, max 2). A
  hint-less iPhone gets neither viewport width nor DPR, so the
  fallback cannot account for its 3x screen.

The failure mode for example project: a 390px-wide iPhone feed card served
the 768px mobile-fallback width is tolerable; but any UA string
misclassified as desktop — iPadOS Safari famously presents a
macOS UA by default ("Request Desktop Website" is the default on
iPad) — gets 1200px. Meanwhile Android Chrome on the same feed
sends `Sec-CH-Viewport-Width: 412` and snaps to 768 (or a tighter
custom breakpoint), with accurate behavior guaranteed by the hint.

## The browser-support disparity

```
Browser              Sends CH width/DPR hints    width=auto path
──────────────────────────────────────────────────────────────────
Chrome 46+           yes                         client hints
Edge 79+             yes                         client hints
Opera 33+            yes                         client hints
Samsung Internet 5+  yes                         client hints
Safari (all)         NO                          UA fallback
iOS Safari (all)     NO                          UA fallback
Firefox (all)        NO                          UA fallback

Global support ~77% of page loads (caniuse, 2026) — but that
number hides the composition: on iOS, EVERY browser (including
"Chrome for iOS") used WebKit and shipped no CH width hints, so
the fallback path covers essentially all iPhone traffic.
```

Treat client hints as progressive enhancement for Chromium users,
never as the primary sizing mechanism for a mobile-heavy product.

## Delegating hints: Accept-CH and Permissions-Policy

Chromium sends `Sec-CH-Viewport-Width` / `Sec-CH-DPR` only after
the server opts in, and by default only to the same origin. example project
serves HTML from Cloudflare Pages and images from a media host, so
cross-origin delegation is required.

```html
<!-- First element in <head>, before any <img>/<link> -->
<meta http-equiv="Delegate-CH"
      content="sec-ch-viewport-width https://media.example.com;
               sec-ch-dpr https://media.example.com" />
```

Or as response headers on the HTML document:

```
Accept-CH: Sec-CH-Viewport-Width, Sec-CH-DPR
Critical-CH: Sec-CH-Viewport-Width
Permissions-Policy: ch-viewport-width=("https://media.example.com"),
                    ch-dpr=("https://media.example.com")
```

`Critical-CH` makes the browser retry the very first navigation
with the hint attached instead of only sending it from the second
request onward. Without delegation, even Chrome users hit the UA
fallback on cross-origin image requests — a common reason
`width=auto` "does nothing" in production while working in a
same-origin test page.

## Save-Data and ECT for low-bandwidth adaptation

`Save-Data: on` is sent without any `Accept-CH` opt-in when the
user enables data saver; `ECT` (values `slow-2g|2g|3g|4g`) needs
opt-in. Both are ideal for a Worker that rewrites transformation
parameters for constrained users:

```js
// Worker fronting media.example.com
export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const saveData = req.headers.get("Save-Data") === "on";
    const ect = req.headers.get("ECT") ?? "4g";
    const slow = saveData || ect === "2g" || ect === "slow-2g";
    return fetch(url.toString(), {
      cf: {
        image: {
          width: "auto",
          format: "auto",
          quality: slow ? 50 : 82,
          // cap DPR upscaling for data-saver users
          dpr: slow ? 1 : 2,
        },
      },
    });
  },
};
```

Note `Save-Data` support is itself Chromium-plus (Safari does not
send it), so this is again enhancement, not a baseline.

## srcset/sizes: the robust cross-browser baseline

Every browser example project cares about — including iOS Safari and
Firefox — implements `srcset`/`sizes`. The browser picks the
candidate from local knowledge (layout width x DPR), no request
headers, no server opt-in, no UA sniffing:

```html
<img

  srcset="
    /cdn-cgi/image/width=320,format=auto/media/abc.jpg   320w,
    /cdn-cgi/image/width=640,format=auto/media/abc.jpg   640w,
    /cdn-cgi/image/width=960,format=auto/media/abc.jpg   960w,
    /cdn-cgi/image/width=1200,format=auto/media/abc.jpg 1200w"
  sizes="(max-width: 640px) 100vw, 640px"
  width="640" height="800" loading="lazy" alt="" />
```

Keep the candidate widths aligned with the `width=auto`
breakpoints so both paths share the same cached variants. With
`srcset` in place, `width=auto` on the `src` fallback is merely a
safety net for contexts that strip markup (RSS, embeds, OG image
fetchers).

## Cache keys and hint fragmentation

```
Approach                     Distinct cached variants per image
──────────────────────────────────────────────────────────────────
width=auto (default)         <= 4 (320/768/960/1200) + fallback
width=auto, 8 wbreakpoints   <= 8 — more precise, worse hit ratio
Vary on raw viewport value   unbounded — never do this
srcset with 4 candidates     <= 4, chosen client-side
```

Breakpoint snapping is the fragmentation control: every viewport
between 321 and 768 shares one 768px cache entry. If you front
transformations with a Worker and build custom logic on hints,
normalize the hint into a small enum before it touches the cache
key, and never emit `Vary: Sec-CH-Viewport-Width` on a raw value.
Transformed variants inherit the original's caching rules
(minimum one hour); purging the original URL purges all variants.

## Anti-patterns

- **Relying on `width=auto` alone for mobile sizing** — Safari,
  iOS Safari, and Firefox never send the hints, so a majority of
  mobile users get the coarse UA fallback. Use `srcset`/`sizes`
  as the baseline; `auto` is a Chromium enhancement.
- **Testing only in Chrome (or DevTools device emulation)** —
  emulated iPhones still send Chrome's client hints. Verify on
  real WebKit, or curl with a Safari UA and no CH headers.
- **Forgetting cross-origin delegation** — without `Delegate-CH`
  or `Permissions-Policy` on the HTML origin, Chrome withholds
  hints from media.example.com and even Chrome users fall back.
- **Varying cache on raw hint values** — unbounded cache-key
  cardinality destroys hit ratio and multiplies billable
  transformations. Snap to breakpoints or a small enum.

## Gotchas

- **iPadOS Safari masquerades as macOS** — desktop UA by default,
  so the UA fallback classifies iPads as desktop and serves the
  1200px width to a tablet on cellular.
- **First-load hint gap** — `Accept-CH` applies from the next
  request; without `Critical-CH` (or the meta tag), the initial
  navigation's images resolve hint-less.
- **`dpr` caps at 2** — a 3x iPhone cannot be fully served even
  when width is known; pick breakpoints assuming ~2x density.
- **Every unique width bills separately** — generous custom
  `wbreakpoints` lists raise the transformation bill as well as
  fragmenting cache.
- **`Save-Data` needs no opt-in but `ECT` does** — include `ECT`
  in `Accept-CH` if the Worker branches on it.

## Verification

- Real-device check: load the feed in iOS Safari and Android
  Chrome; compare `content-length` of the same feed image.
- `curl -H "User-Agent: <mobile Safari UA>" -sI <transform URL>`
  vs the same request plus `-H "Sec-CH-Viewport-Width: 390"` —
  confirm the fallback width matches `wmobile` expectations.
- HTML response includes `Accept-CH`/`Critical-CH` and
  `Permissions-Policy` (or the `Delegate-CH` meta tag) delegating
  to the media origin.
- Feed `<img>` elements ship `srcset` + `sizes` with candidate
  widths matching the transformation breakpoints.
- RUM segmented by browser: image bytes per session for iOS
  Safari should converge with Android Chrome after the fix.

## Related

- `documentation/docs/policies/cloudflare/images-best-practices.md`
- `documentation/docs/policies/frontend/html-srcset-responsive-images.md`
- `documentation/docs/policies/performance/image-cdn-transform-pipelines.md`
- `documentation/docs/policies/performance/image-optimization-webp-avif.md`

## Source URLs (verified 2026-08-17)

- Make responsive images (Cloudflare Images) — https://developers.cloudflare.com/images/optimization/make-responsive-images/
- Transform via URL (Cloudflare Images) — https://developers.cloudflare.com/images/transform-images/transform-via-url/
- Client Hints: DPR, Width, Viewport-Width (caniuse) — https://caniuse.com/client-hints-dpr-width-viewport
- Adapting to users with Client Hints — https://web.dev/articles/performance-optimizing-content-efficiency-client-hints
- Save-Data header (MDN) — https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Save-Data
