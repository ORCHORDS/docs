# Flutter Image Loading via Cloudflare Workers Image Resizing

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
A Flutter app serving full-resolution images from Cloudflare R2 wastes bandwidth and causes jank on low-end devices, because the same 4 MB source image is downloaded regardless of the widget's actual display size or device pixel ratio.

## Context
Cloudflare Workers Image Resizing (`/cdn-cgi/image/...`) transforms and re-encodes images at the edge on demand. A thin Worker proxy in front of R2 builds the resize URL, enforces allowed dimensions, and adds long-lived cache headers. Flutter's `cached_network_image` package caches the already-resized variant, so each physical size is fetched at most once per device.

## Cloudflare Worker — Image Transform Proxy
```typescript
// workers/image-proxy.ts
import { Env } from './types';

interface ResizeOptions {
  width?: number;
  height?: number;
  fit?: 'cover' | 'contain' | 'crop' | 'pad';
  format?: 'auto' | 'webp' | 'avif' | 'jpeg' | 'png';
  quality?: number;
  dpr?: number;
}

const ALLOWED_WIDTHS  = new Set([64, 128, 256, 384, 512, 768, 1024, 1536, 2048]);
const MAX_DPR         = 3;

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url  = new URL(req.url);
    // Path: /img/{key}?w=256&h=256&fit=cover&fmt=auto&dpr=2
    const key  = url.pathname.replace(/^\/img\//, '');
    if (!key) return new Response('Missing image key', { status: 400 });

    const rawW = Number(url.searchParams.get('w') ?? '0');
    const rawH = Number(url.searchParams.get('h') ?? '0');
    const dpr  = Math.min(Number(url.searchParams.get('dpr') ?? '1'), MAX_DPR);
    // Snap requested width to nearest allowed bucket to maximise cache hit rate
    const width = snapWidth(rawW > 0 ? Math.round(rawW * dpr) : 0);

    const opts: ResizeOptions = {
      width:   width  || undefined,
      height:  rawH   ? Math.round(rawH * dpr) : undefined,
      fit:     (url.searchParams.get('fit') as ResizeOptions['fit']) ?? 'cover',
      format:  'auto',
      quality: 80,
    };

    // Build the Cloudflare Image Resizing URL targeting R2's S3-compatible endpoint
    const sourceUrl = `https://${env.R2_PUBLIC_HOSTNAME}/${key}`;
    const cfParams  = Object.entries(opts)
      .filter(([, v]) => v !== undefined)
      .map(([k, v]) => `${k}=${v}`)
      .join(',');

    const resizeUrl = `https://${url.hostname}/cdn-cgi/image/${cfParams}/${sourceUrl}`;

    const imageRes = await fetch(resizeUrl, {
      cf: { image: opts },   // alternative: use cf.image directly when on a zone with IR enabled
    });

    if (!imageRes.ok) {
      return new Response('Image not found', { status: 404 });
    }

    return new Response(imageRes.body, {
      status: 200,
      headers: {
        'Content-Type':  imageRes.headers.get('Content-Type') ?? 'image/webp',
        'Cache-Control': 'public, max-age=31536000, immutable',
        'Vary':          'Accept',     // serve AVIF to supporting clients, JPEG to others
      },
    });
  },
};

function snapWidth(requested: number): number {
  if (requested <= 0) return 0;
  for (const w of ALLOWED_WIDTHS) { if (requested <= w) return w; }
  return 2048;
}
```

## Flutter — Image URL Builder
```dart
// lib/services/image_cdn.dart
import 'dart:ui';
import 'package:flutter/widgets.dart';

class ImageCdn {
  static const _baseUrl = 'https://api.example.com/img';

  /// Builds a CDN URL for [key] sized to [logicalWidth] × [logicalHeight]
  /// CSS pixels, automatically applying the device pixel ratio.
  static String url(
    BuildContext context,
    String key, {
    double? logicalWidth,
    double? logicalHeight,
    String fit = 'cover',
  }) {
    final dpr = MediaQuery.devicePixelRatioOf(context);
    final params = <String, String>{
      if (logicalWidth  != null) 'w': logicalWidth.round().toString(),
      if (logicalHeight != null) 'h': logicalHeight.round().toString(),
      'fit': fit,
      'dpr': dpr.toStringAsFixed(1),
    };
    final query = params.entries.map((e) => '${e.key}=${e.value}').join('&');
    return '$_baseUrl/${Uri.encodeComponent(key)}?$query';
  }

  /// Convenience: fit inside a square of [size] logical pixels.
  static String square(BuildContext context, String key, double size) =>
      url(context, key, logicalWidth: size, logicalHeight: size, fit: 'cover');

  /// Convenience: full-width banner image.
  static String banner(BuildContext context, String key) {
    final screenW = MediaQuery.sizeOf(context).width;
    return url(context, key, logicalWidth: screenW, fit: 'crop');
  }
}
```

## Flutter — CachedNetworkImage Integration
```dart
// lib/widgets/cdn_image.dart
import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import '../services/image_cdn.dart';

class CdnImage extends StatelessWidget {
  const CdnImage({
    super.key,
    required this.imageKey,
    this.width,
    this.height,
    this.fit = BoxFit.cover,
    this.placeholder,
    this.errorWidget,
  });

  final String      imageKey;
  final double?     width;
  final double?     height;
  final BoxFit      fit;
  final Widget?     placeholder;
  final Widget?     errorWidget;

  @override
  Widget build(BuildContext context) {
    final cdnUrl = ImageCdn.url(
      context,
      imageKey,
      logicalWidth:  width,
      logicalHeight: height,
      fit: _boxFitToCf(fit),
    );

    return CachedNetworkImage(
      imageUrl: cdnUrl,
      width:  width,
      height: height,
      fit:    fit,
      maxWidthDiskCache:  2048,
      maxHeightDiskCache: 2048,
      placeholder: (_, __) => placeholder ?? const _Shimmer(),
      errorWidget: (_, __, ___) =>
          errorWidget ?? const Icon(Icons.broken_image_outlined),
    );
  }

  static String _boxFitToCf(BoxFit fit) => switch (fit) {
    BoxFit.cover   => 'cover',
    BoxFit.contain => 'contain',
    BoxFit.fill    => 'crop',
    _              => 'cover',
  };
}

class _Shimmer extends StatelessWidget {
  const _Shimmer();

  @override
  Widget build(BuildContext context) => DecoratedBox(
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surfaceVariant,
          borderRadius: BorderRadius.circular(4),
        ),
      );
}
```

## Responsive Grid Usage
```dart
// lib/screens/gallery_screen.dart
class GalleryScreen extends StatelessWidget {
  const GalleryScreen({super.key, required this.items});
  final List<GalleryItem> items;

  @override
  Widget build(BuildContext context) {
    final cols      = MediaQuery.sizeOf(context).width > 600 ? 3 : 2;
    final tileSize  = MediaQuery.sizeOf(context).width / cols;

    return GridView.builder(
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: cols,
        childAspectRatio: 1,
      ),
      itemCount: items.length,
      itemBuilder: (ctx, i) => CdnImage(
        imageKey:  items[i].r2Key,
        width:     tileSize,
        height:    tileSize,
      ),
    );
  }
}
```

## Anti-patterns
- Building the resize URL inside a `StatelessWidget.build` without caching — every rebuild constructs a new URL, evicting `CachedNetworkImage`'s memory cache entry.
- Requesting exact logical-pixel sizes without snapping to width buckets — produces hundreds of unique cache keys at the edge, lowering the cache hit ratio.
- Omitting `dpr` from the URL — serves 1× images to 3× screens, making images appear blurry.
- Using `Image.network` instead of `CachedNetworkImage` — re-downloads on every scroll-off and on hot restart.
- Allowing arbitrary `w`/`h` query parameters on the Worker without allowlisting — enables DoS via infinite unique resize jobs.

## Gotchas
- Cloudflare Image Resizing requires a paid Workers plan and must be enabled per zone in the dashboard; the `/cdn-cgi/image/` path returns 400 otherwise.
- `format=auto` serves AVIF to Android 12+ and modern iOS but falls back to WebP/JPEG for older OS versions based on the `Accept` header — Flutter's HTTP client does not send `Accept: image/avif` by default; set it on the Worker based on `dpr` as a proxy for device capability.
- `cached_network_image` stores images keyed by URL — changing any parameter (even formatting) creates a new cache entry and the old one is orphaned until LRU eviction.
- The Worker's `cf.image` option only works when the request originates from Cloudflare's network (on your zone), not from localhost dev environments; use a fallback direct R2 URL during local development.

## Verification
1. Open Flutter DevTools → Network tab and confirm image responses include `Cache-Control: public, max-age=31536000, immutable`.
2. Scroll through a 100-item grid twice and assert that total network bytes for the second scroll is 0 (all served from disk cache).
3. On a 3× OLED device, confirm returned image dimensions are 3× the logical tile size.
4. Test on a 1× emulator and confirm the Worker receives `dpr=1.0` and returns a proportionally smaller image.
5. Check Cloudflare Analytics → Cache → Hit Rate; CDN images should show ≥ 95% cache hit rate after warm-up.

## Related
- [flutter-workers-dart-client.md](flutter-workers-dart-client.md)
- [mobile-image-caching-patterns.md](mobile-image-caching-patterns.md)
- [image-upload-compression-client-side.md](image-upload-compression-client-side.md)
- [cloudflare-workers-ai-mobile-inference-edge.md](cloudflare-workers-ai-mobile-inference-edge.md)
- [mobile-app-size-optimization.md](mobile-app-size-optimization.md)

## Sources
- Cloudflare Image Resizing docs: https://developers.cloudflare.com/images/image-resizing/
- cached_network_image pub.dev: https://pub.dev/packages/cached_network_image
- Flutter MediaQuery devicePixelRatio: https://api.flutter.dev/flutter/widgets/MediaQueryData/devicePixelRatio.html
- Cloudflare R2 public buckets: https://developers.cloudflare.com/r2/buckets/public-buckets/
