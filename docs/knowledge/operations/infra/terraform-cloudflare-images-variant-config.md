# Terraform Cloudflare Images Variant Configuration

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your application serves user-uploaded images through Cloudflare Images and you need multiple delivery variants — thumbnails, open-graph cards, full-width heroes — without maintaining a separate image processing service. Variants must be reproducible across staging and production accounts with consistent names and dimensions.

## Context

Cloudflare Images Variants define how a stored image is resized and cropped on delivery. Each variant has a name, a fit mode (`scale-down`, `contain`, `cover`, `crop`, `pad`), optional width/height constraints, and a metadata-stripping toggle. The Terraform resource `cloudflare_images_variant` (provider ≥ 4.20) manages variants under an account — variant names are global to the account and shared across all images. The `never_require_signed_urls` flag overrides the zone-level signed URL requirement for a specific variant.

---

## Provider Setup

```hcl
# versions.tf
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.36"
    }
  }
  required_version = ">= 1.9"
}

provider "cloudflare" {
  api_token = <redacted-secret>
}

variable "cloudflare_api_token" {
  type      = string
  sensitive = true
}

variable "account_id" {
  type = string
}
```

## Defining Core Variants

```hcl
# variants.tf

# Thumbnail — square crop for avatars and cards
resource "cloudflare_images_variant" "thumbnail" {
  account_id = var.account_id
  variant_id = "thumbnail"

  options {
    fit      = "cover"
    width    = 200
    height   = 200
    metadata = "none"   # strip EXIF/IPTC — saves bytes, protects privacy
  }

  never_require_signed_urls = false
}

# Open-graph social card — 1200×630 with letterboxing
resource "cloudflare_images_variant" "og" {
  account_id = var.account_id
  variant_id = "og"

  options {
    fit      = "pad"    # pad with transparent/white background
    width    = 1200
    height   = 630
    metadata = "none"
  }

  never_require_signed_urls = true   # OG crawlers cannot sign URLs
}

# Hero — full-width, height-constrained, no crop
resource "cloudflare_images_variant" "hero" {
  account_id = var.account_id
  variant_id = "hero"

  options {
    fit      = "scale-down"
    width    = 1920
    height   = 800
    metadata = "keep"   # retain colour profile for professional images
  }

  never_require_signed_urls = false
}

# Public variant — no auth, served from imagedelivery.net
resource "cloudflare_images_variant" "public" {
  account_id = var.account_id
  variant_id = "public"

  options {
    fit      = "contain"
    width    = 800
    height   = 600
    metadata = "none"
  }

  never_require_signed_urls = true
}
```

## Variants via a Map for DRY Config

```hcl
# variables.tf
variable "image_variants" {
  type = map(object({
    fit                      = string
    width                    = number
    height                   = number
    metadata                 = string
    never_require_signed_urls = bool
  }))

  default = {
    thumbnail = { fit = "cover",      width = 200,  height = 200,  metadata = "none", never_require_signed_urls = false }
    og        = { fit = "pad",        width = 1200, height = 630,  metadata = "none", never_require_signed_urls = true  }
    hero      = { fit = "scale-down", width = 1920, height = 800,  metadata = "keep", never_require_signed_urls = false }
    avatar    = { fit = "cover",      width = 64,   height = 64,   metadata = "none", never_require_signed_urls = false }
    preview   = { fit = "contain",    width = 400,  height = 300,  metadata = "none", never_require_signed_urls = true  }
  }
}

# main.tf
resource "cloudflare_images_variant" "all" {
  for_each   = var.image_variants
  account_id = var.account_id
  variant_id = each.key

  options {
    fit      = each.value.fit
    width    = each.value.width
    height   = each.value.height
    metadata = each.value.metadata
  }

  never_require_signed_urls = each.value.never_require_signed_urls
}
```

## Outputs for Application Config

```hcl
# outputs.tf
output "variant_delivery_urls" {
  description = "Base URL pattern per variant — append /<image-id>/<variant> at runtime"
  value = {
    for k, v in cloudflare_images_variant.all : k => "https://imagedelivery.net/<hash>/<image-id>/${v.variant_id}"
  }
}

output "variant_ids" {
  description = "Variant IDs for use in application environment config"
  value       = keys(cloudflare_images_variant.all)
}
```

## Fit Mode Reference

```hcl
# fit modes — inline documentation as locals for clarity in large configs
locals {
  fit_modes = {
    "scale-down" = "Shrinks only; never enlarges. Preserves aspect ratio."
    "contain"    = "Fits within box, preserving aspect ratio. May letterbox."
    "cover"      = "Fills box exactly, crops overflow. Best for fixed-ratio slots."
    "crop"       = "Crops to exact dimensions without resizing first."
    "pad"        = "Like contain but fills padding with background colour."
  }
}

# Example: cover variant with explicit background for pad mode
resource "cloudflare_images_variant" "padded_white" {
  account_id = var.account_id
  variant_id = "padded_white"

  options {
    fit        = "pad"
    width      = 800
    height     = 600
    metadata   = "none"
    background = "#ffffff"   # only valid with fit = "pad"
  }

  never_require_signed_urls = true
}
```

---

## Anti-patterns

- **Using `crop` for avatars**: `crop` anchors to the top-left corner, cutting off faces. Use `cover` with gravity or `thumbnail` for face-detection crops.
- **Keeping metadata on public variants**: EXIF can expose GPS coordinates from mobile uploads. Always set `metadata = "none"` on public-facing variants.
- **Hardcoding variant names in application code**: Export variant names as Terraform outputs and inject them via environment variables so renames are a single `terraform apply`.
- **Setting `never_require_signed_urls = true` on internal variants**: If your account uses signed URLs for access control, accidentally opening a variant is a data exposure.
- **Omitting width and height**: Cloudflare will serve the original dimensions, defeating the variant's purpose and inflating egress.

## Gotchas

- `variant_id` must be unique per account — not per zone. A staging and production account share nothing, but a single account used for both environments will have collisions.
- Variant deletion is blocked if images are actively being served through it; Terraform will error. You need to remove references in the application first.
- The `background` attribute is silently ignored for fit modes other than `pad`.
- `metadata = "keep"` still strips GPS data in some Cloudflare plan tiers — verify behaviour for your plan.
- Cloudflare Images is billed per stored image and per delivery, not per variant — creating many variants is free until images are delivered through them.

## Verification

```bash
# List all variants via API
curl -s "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/images/v1/variants" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result.variants | keys'

# Inspect a specific variant
curl -s "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/images/v1/variants/thumbnail" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result.variant.options'

# Test delivery URL (replace hash and image-id)
curl -sI "https://imagedelivery.net/<account-hash>/<image-id>/thumbnail"
# Expect: HTTP/2 200, content-type: image/webp (or jpeg)
```

## Related

- `cloudflare-r2-presigned-urls-workers.md`
- `pulumi-cloudflare-r2-cors-policy.md`
- `terraform-cloudflare-workers-custom-domain-routing.md`

## Sources

- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/images_variant
- https://developers.cloudflare.com/images/transform-images/resize-with-workers/
- https://developers.cloudflare.com/images/cloudflare-images/serve-images/
- https://developers.cloudflare.com/images/cloudflare-images/transform/fit-modes/
