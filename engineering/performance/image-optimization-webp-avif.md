# Image Optimization: WebP and AVIF

## What are WebP and AVIF?

WebP and AVIF are modern image formats that provide superior compression compared to traditional JPEG and PNG formats. WebP offers lossy compression with 25-35% smaller file sizes, while AVIF delivers even better compression at 40-50% smaller files with support for both lossy and lossless modes.

## Compression Ratios

AVIF typically achieves 40-50% smaller file sizes than JPEG, while WebP provides 25-35% savings. For example:
```bash
# JPEG: 100KB
# WebP: 60KB (40% smaller)
# AVIF: 50KB (50% smaller)
```

## Responsive Images with srcset

Use the `srcset` attribute to serve different image formats based on device capabilities:
```html
<picture>
  <source srcset="image.avif" type="image/avif">
  <source srcset="image.webp" type="image/webp">
  <img  alt="Description">
</picture>
```

## The Picture Element

The `<picture>` element allows browsers to choose the best format:
```html
<picture>
  <source media="(max-width: 768px)" srcset="mobile.avif" type="image/avif">
  <source media="(max-width: 768px)" srcset="mobile.webp" type="image/webp">
  <img  alt="Description" loading="lazy">
</picture>
```

## CDN Auto-Format

Modern CDNs automatically convert images to optimal formats:
```html
<!-- Cloudflare example -->
<img  alt="Photo">
```

## Quality Settings

Control compression quality with specific parameters:
```html
<!-- WebP quality 80% -->
<img  alt="Photo">

<!-- AVIF with quality settings -->
<img  alt="Photo">
```

## Common pitfalls

Avoid serving images to unsupported browsers by testing format support. Never assume all browsers support AVIF or WebP. Always provide fallback JPEG/PNG images. Don't optimize images too aggressively, as quality loss becomes noticeable at compression levels above 90%. Remember that AVIF requires more CPU processing time during encoding compared to WebP. Test across different devices and browsers to ensure compatibility.
