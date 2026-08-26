# Image Format Negotiation at the Cloudflare Edge (Mobile vs Desktop)

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

example project (example.com) serves user media from R2 through Cloudflare
Image Transformations with `format=auto`. Desktop Chrome users get
AVIF at ~40% of the JPEG byte size, but analytics show the heaviest
image payloads land on the oldest phones: an iPhone 8 stuck on iOS
16-incapable firmware pulls full JPEGs over LTE while a desktop on
fiber gets tiny AVIFs — exactly backwards from what a metered-data
mobile fleet needs. Meanwhile cache hit ratio dropped after
enabling format negotiation, because the same URL now caches
multiple format variants across a mixed browser fleet.

## Context

`format=auto` performs content negotiation at the edge: Cloudflare
inspects the request's `Accept` header and serves the most
efficient format the browser *advertises* — AVIF or WebP — falling
back to the original JPEG/PNG otherwise. Negotiation keys on the
Accept header, not on actual decode capability, so a browser that
can decode a format but does not advertise it (Safari and AVIF for
years) silently gets the larger file. Because format now varies per
request for one URL, caching relies on Cloudflare's "Vary for
images" — the only place Cloudflare's cache honors `Vary` at all —
which multiplies cache entries per asset. This entry covers format
selection only; width/DPR client-hint sizing is covered in
`client-hints-adaptive-image-delivery-mobile.md`.

## How format=auto picks a format

```
GET /cdn-cgi/image/format=auto,width=768/media/abc.jpg
Accept: image/avif,image/webp,image/apng,*/*;q=0.8

        ┌────────────────────────────────┐
        │ Accept advertises image/avif?  │
        └──────┬──────────────────┬──────┘
          yes  │                  │ no
               ▼                  ▼
         encode AVIF*    ┌─────────────────────┐
                         │ advertises webp?    │
                         └───┬─────────────┬───┘
                        yes  │             │ no
                             ▼             ▼
                       encode WebP    original format
                                      (JPEG / PNG)

* unless the source is too large to encode AVIF within the
  time budget — Cloudflare then silently falls back to
  WebP/JPEG rather than time out (AVIF encode is roughly an
  order of magnitude slower than WebP/JPEG encode).
```

In a Worker using the `cf.image` binding you implement the same
negotiation yourself — `format: "auto"` is a URL-mode convenience:

```js
const accept = request.headers.get("accept") || "";
const image = { width: 768, quality: 85, fit: "scale-down" };
if (/image\/avif/.test(accept)) {
  image.format = "avif";
} else if (/image\/webp/.test(accept)) {
  image.format = "webp";
} // else: leave original format (JPEG/PNG)
return fetch(originUrl, { cf: { image } });
```

## Browser format support matrix (as of 2026)

```
Format   Chrome/Edge     Firefox        Safari/iOS         Advertised
                                                           in Accept?
──────────────────────────────────────────────────────────────────────
WebP     since 2014      since v65      Safari 14+ /       yes (all)
         (v32+)          (2019)         iOS 14+ (2020)
AVIF     v85+ (2020),    v93+ (2021)    Safari 16+ /       Chromium +
         Android too                    iOS 16+ (2022)     Firefox yes;
                                                           Safari late/
                                                           inconsistent
JPEG XL  v145 (Feb 2026) v152 (Jun      Safari 17+         effectively
         behind flag,    2026) behind   (2023, decode      no
         NOT default     pref, NOT      only; no
                         default        progressive)
```

- Chromium reversed its 2022 "JPEG XL is obsolete" decision in
  Nov 2025; Chrome 145 ships a Rust decoder behind
  `chrome://flags/#enable-jxl-image-format`. Default-on is
  expected but not live as of mid-2026. Browsers decoding JXL
  without user action are only ~14% of visitors, and Cloudflare
  Image Transformations do not emit JXL — `format=auto` chooses
  between AVIF, WebP, and the original only. Do not plan around
  JXL yet.
- Safari added AVIF *decoding* in 16.0 but for a long time did not
  advertise `image/avif` in its Accept header, so Accept-keyed
  negotiation (Cloudflare's included) serves Safari WebP even on
  AVIF-capable devices. Treat "Safari gets WebP" as the working
  assumption and verify per-version (see Verification).

## The backwards disparity on old mobile devices

Safari version is pinned to the OS, and iPhones age out of iOS
updates. The device least able to afford bytes gets the biggest
files:

```
Device (max OS)          Best format via     Relative bytes for
                         format=auto         the same 768w photo
──────────────────────────────────────────────────────────────────
iPhone 6s/7 (iOS 15)     WebP                ~0.70x of JPEG
iPhone 6 (iOS 12)        JPEG (original)     1.00x
iPhone X+ on iOS 16+     WebP (Safari        ~0.70x
                         Accept-limited)
Old Android, evergreen   AVIF                ~0.50x or less
Chrome (auto-updates)
Desktop Chrome/Firefox   AVIF                ~0.50x or less
```

Android is mostly fine — Chrome auto-updates independently of the
OS, so even old Androids advertise AVIF. The problem population is
old iPhones on metered connections: they get JPEG or WebP over the
slowest links. Mitigations that actually help them:

- Cap intrinsic bytes regardless of format: explicit `width=` per
  slot and `quality=75`-ish for feed thumbnails, so the JPEG
  fallback is a small JPEG.
- Use `slow-connection-quality=50` (or similar) to degrade quality
  when the client signals a slow connection: triggered by
  `Save-Data: on`, RTT > 150 ms, ECT slow-2g/2g/3g, or downlink
  < 5 Mbps. Caveat: these are client hints, which Safari does not
  send — so this lever also skips the iPhone fleet and mainly
  helps old Androids (`Save-Data` being the most reliable signal).

## Vary: Accept and cache hit ratio

Cloudflare's cache normally *ignores* the `Vary` response header.
"Vary for images" is the single exception: on Pro/Business/
Enterprise zones, when the origin sends `Vary: Accept` on an image
extension (.avif .bmp .gif .jpg .jpeg .jp2 .png .tif .tiff .webp),
the edge parses the request Accept header and caches each format
variant separately under the same URL.

```
One URL, mixed fleet, Vary: Accept active:

  /media/abc.jpg ──► cache entry #1  AVIF  (Chromium/Firefox)
                 ──► cache entry #2  WebP  (Safari 14-18)
                 ──► cache entry #3  JPEG  (legacy / Accept: */*)

Effect: up to 3x entries per asset. First requester per
variant per colo is a MISS → cold-cache hit ratio drops on
exactly the long-tail UGC that was barely cached once.
```

- Variants are keyed by parsed format preference, not the raw
  Accept string — fan-out is bounded by formats emitted (2-3).
- Requires the extension in the URL path — `?file=abc.jpg` query
  strings do not vary.
- The origin must return the extension's format when the request
  has no Accept header or `Accept: */*`, or crawlers/legacy
  clients get mislabeled bytes.
- Transformation results themselves are cached for one hour or
  longer per origin `Cache-Control`; all variants share cache
  under the *source* image URL, so purge the original URL, not
  the `/cdn-cgi/image/...` URL.

## Polish vs Image Transformations

```
                    Polish                Image Transformations
──────────────────────────────────────────────────────────────────
What it does        auto-recompress +     on-the-fly resize/
                    strip metadata on     re-encode via
                    origin-pulled         /cdn-cgi/image/... or
                    assets, as cached     Worker cf.image
URL changes         none                  yes (new URLs)
WebP/AVIF           WebP toggle; format   format=auto negotiates
                    conversion is         AVIF/WebP per request
                    Polish-managed
Plans               Pro+ (no Free)        any zone with
                                          transformations enabled
Use at example project      static site assets    all R2 user media
```

Do not stack them: transformation output is already optimized and
Polish only touches origin-pulled assets. Pick per asset class.

## Anti-patterns

- **Assuming format=auto means every mobile user gets the small
  file** — negotiation follows the Accept header. Old iPhones and
  Accept-conservative Safari versions get WebP or JPEG; only
  evergreen Chromium/Firefox reliably get AVIF.
- **Enabling Vary: Accept on a Free zone and expecting variant
  caching** — Vary for images is Pro+. On Free, format-varied
  responses risk serving one cached format to every browser.
- **Pre-encoding JXL for Safari** — Safari's JXL decode is
  incomplete (no progressive), Chrome/Firefox ship it off by
  default in 2026, and Cloudflare will not emit it. AVIF+WebP+JPEG
  is the complete 2026 set.
- **Purging /cdn-cgi/image/ URLs after a moderation takedown** —
  variants cache under the source URL. Purge the R2/origin URL or
  removed example project media stays visible up to the cache TTL.

## Gotchas

- **AVIF encode fallback is silent** — large sources skip AVIF to
  avoid encode timeouts (AVIF is ~10x slower to encode) and return
  WebP/JPEG with no error. If big uploads never come back AVIF,
  that is by design; downscale first (chained width + format).
- **The JPEG fallback defines worst-case bytes** — quality=85 JPEG
  can be 2-3x the AVIF at similar perceived quality. Budget the
  fallback, not the best case, when estimating mobile data cost.
- **slow-connection-quality never fires for Safari** — it depends
  on client hints (Save-Data/RTT/ECT/Downlink) that Safari does
  not send. The save-data lever helps the Android half of the
  fleet only.
- **Workers calling Workers drop transformations** — a second
  Worker on the request chain loses the resize, `Cf-Resized`
  disappears, and originals pass through at full size.

## Verification

- Per device class, check delivered format in DevTools/proxy:
  `content-type: image/avif` vs `image/webp` vs `image/jpeg` on
  feed image responses (remote-inspect a real iPhone; emulators
  send desktop Accept headers).
- Confirm `Cf-Resized` is present on transformed responses; absent
  means resizing never ran, `err=94xx` codes name the failure
  (9401 bad args ... 9529 processing timeout).
- ETag on a transformed response looks like
  `cf-<hash>:<original-etag>` — compare the suffix with the R2
  object's ETag to confirm freshness after re-upload.
- Compare bytes for one asset across formats by forcing
  `format=avif` / `format=webp` / `format=jpeg` and recording
  content-length; validate the AVIF savings claim on real example project
  media, not stock photos.
- After enabling Vary: Accept, watch cache hit ratio per
  content-type in Cache Analytics for the expected initial dip
  and recovery.

## Related

- `documentation/categories/cloudflare/client-hints-adaptive-image-delivery-mobile.md`
- `documentation/categories/cloudflare/images-best-practices.md`
- `documentation/categories/performance/image-cdn-transform-pipelines.md`

## Source URLs (verified 2026-08-17)

- Transform via URL (format=auto, slow-connection-quality) —
  https://developers.cloudflare.com/images/transform-images/transform-via-url/
- Vary for images — https://developers.cloudflare.com/cache/advanced-configuration/vary-for-images/
- Troubleshooting / Cf-Resized — https://developers.cloudflare.com/images/reference/troubleshooting/
- Cloudflare Polish — https://developers.cloudflare.com/images/polish/
- Chromium re-adds JPEG XL (Nov 2025) — https://www.devclass.com/development/2025/11/24/googles-chromium-team-decides-it-will-add-jpeg-xl-support-reverses-obsolete-declaration/1730949
