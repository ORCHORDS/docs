# images-best-practices

**Issue:** Cloudflare Images — transform, optimize, serve
**Date:** 2026-08-09
**Status:** documented

## Symptom
You serve images. Users on mobile get 2MB images.
The page is slow. You wish the images were smaller.

## Root cause
**Unoptimized images are huge.** Use Cloudflare
Images.

**Source:** CF Images:
https://developers.cloudflare.com/images/

## The "Image Resizing" pattern

For image resizing:
```
https://example.com/cdn-cgi/image/width=800,quality=80,format=auto/image.jpg
```

The image is resized on the fly.

## The "transformations" pattern

For transformations:
- **Width:** `width=800`
- **Height:** `height=600`
- **Quality:** `quality=80`
- **Format:** `format=auto` (WebP, AVIF)
- **Fit:** `fit=cover` / `contain` / `crop`
- **Gravity:** `gravity=auto` (face detection)

```html
<img
  src="https://example.com/cdn-cgi/image/width=400,quality=80,format=auto/profile.jpg"
  alt="Profile"
  loading="lazy"
  width="400"
  height="400"
/>
```

The image is transformed.

## The "responsive images" pattern

For responsive:
```html
<img
  src="https://example.com/cdn-cgi/image/width=400/profile.jpg"
  srcset="
    https://example.com/cdn-cgi/image/width=400/profile.jpg 400w,
    https://example.com/cdn-cgi/image/width=800/profile.jpg 800w,
    https://example.com/cdn-cgi/image/width=1200/profile.jpg 1200w
  "
  sizes="(max-width: 600px) 400px, 800px"
  alt="Profile"
/>
```

The image is responsive.

## The "format auto" pattern

For format auto:
- **WebP:** Modern, smaller
- **AVIF:** Newest, smallest
- **JPEG fallback:** Old browsers

```ts
// CF picks the best format for the user's browser
const src = 'https://example.com/cdn-cgi/image/format=auto/image.jpg';
```

The format is auto.

## The "face detection" pattern

For face detection:
```
https://example.com/cdn-cgi/image/width=400,height=400,fit=cover,gravity=face/profile.jpg
```

The image is cropped to the face.

## The "watermark" pattern

For watermarks:
```
https://example.com/cdn-cgi/image/watermark=https://example.com/logo.png,gravity=southeast,opacity=50/image.jpg
```

The watermark is applied.

## The "blur" pattern

For blur (placeholders):
```
https://example.com/cdn-cgi/image/width=20,quality=30,blur=10/image.jpg
```

The image is blurred.

## The "Image Resizing limits" pattern

For limits:
- **Source size:** Unlimited
- **Source format:** JPEG, PNG, WebP, GIF, AVIF
- **Output format:** Same + WebP, AVIF
- **Transformations:** Width, height, fit, gravity, etc.

The limits are checked.

## The "Image Resizing cost" pattern

For cost:
- **Image Resizing:** $1/100k transformations (paid)
- **Free tier:** Limited
- **Custom transformations:** Paid only

The cost is per transformation.

## The "Image Resizing vs Images" choice

| Use case | Use |
|---|---|
| **Transform existing** | Image Resizing |
| **Store + transform** | Images |
| **On-the-fly** | Image Resizing |
| **Variants** | Images |

For most apps, **Image Resizing** is enough.

## The "Images" pattern

For Cloudflare Images (full):
```toml
# wrangler.toml
[images]
binding = "IMAGES"
```

```ts
// Direct upload
const upload = await fetch('https://api.cloudflare.com/client/v4/accounts/.../images/v1', {
  method: 'POST',
  body: formData,  // File
});

// Variant URL
const variantUrl = `https://imagedelivery.net/<account_hash>/<image_id>/<variant_name>`;
```

The image is uploaded + served via variant.

## The "image anti-pattern" anti-patterns

### 1. Big images
- **Issue:** Slow page
- **Fix:** Resize + WebP

### 2. No lazy loading
- **Issue:** Eager load
- **Fix:** loading="lazy"

### 3. No width/height
- **Issue:** Layout shift
- **Fix:** Always set

### 4. Wrong format
- **Issue:** PNG for photos
- **Fix:** JPEG / WebP

### 5. No responsive
- **Issue:** Mobile gets desktop size
- **Fix:** srcset

## Verification
- **Test:** Image loads
- **Test:** Transform works
- **Test:** Lazy load works
- **Live:** Image size monitored
- **Audit:** Quarterly review

## Gotchas
- **The "big images" anti-pattern.** Resize.
- **The "no width/height" anti-pattern.** Always set.
- **The "no responsive" anti-pattern.** Use srcset.

## Related
- `feature-cookbook-frontend.md`
- `feature-cookbook-frontend-patterns.md`
- `cloudflare/r2-best-practices.md`
- CF Images: https://developers.cloudflare.com/images/
