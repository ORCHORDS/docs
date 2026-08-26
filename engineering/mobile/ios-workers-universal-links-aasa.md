# iOS Universal Links: AASA File Served from Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
iOS Universal Links require Apple to fetch the `apple-app-site-association` (AASA) file from your domain over HTTPS before it will open links in your app. Serving this file from a Cloudflare Worker gives you zero-cold-start latency, a globally distributed CDN, and the ability to update path rules without a native release.

## Context
Apple's CDN pre-fetches the AASA file when an app is installed, and re-fetches it periodically. The file must be served at `https://<domain>/.well-known/apple-apple-site-association` with `Content-Type: application/json` and no redirect chain longer than one hop. Workers handle the response in under 1 ms globally, and Cloudflare's cache automatically absorbs Apple's batch fetches.

## Serving the AASA File

```typescript
// worker/src/index.ts
import { Env } from './types';

const AASA_PATH = '/.well-known/apple-app-site-association';
// Legacy path — some older iOS versions still probe this
const AASA_PATH_LEGACY = '/apple-app-site-association';

const aasa = {
  applinks: {
    details: [
      {
        appIDs: ['TEAMID1234.com.example.myapp'],
        components: [
          // Open /products/* in app
          { '/': '/products/*', comment: 'Product detail pages' },
          // Open /orders/* in app, excluding /orders/history
          { '/': '/orders/*', exclude: true, '/': '/orders/history' },
          { '/': '/orders/*' },
          // Open password-reset links in app
          { '/': '/reset-password', queryItems: [{ name: 'token', value: '?*' }] },
        ],
      },
    ],
  },
  // Enable web credentials (Shared Web Credentials / Passwords AutoFill)
  webcredentials: {
    apps: ['TEAMID1234.com.example.myapp'],
  },
};

function aasaResponse(): Response {
  return new Response(JSON.stringify(aasa, null, 2), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      // Cache for 1 hour — Apple CDN re-fetches on its own schedule
      'Cache-Control': 'public, max-age=3600',
      // Required: must not redirect, Apple follows at most one
      'Vary': 'Accept-Encoding',
    },
  });
}

export default {
  async fetch(request: Request, _env: Env): Promise<Response> {
    const { pathname } = new URL(request.url);

    if (pathname === AASA_PATH || pathname === AASA_PATH_LEGACY) {
      return aasaResponse();
    }

    // Fall through to your app's normal routing
    return new Response('Not found', { status: 404 });
  },
};
```

## Dynamic AASA from KV (Multi-tenant or A/B)

For apps with multiple team IDs or staged rollouts, store the AASA config in KV and serve it dynamically:

```typescript
// worker/src/dynamic-aasa.ts
import { Env } from './types';

interface AasaConfig {
  appIDs: string[];
  components: object[];
  webcredentials?: string[];
}

export async function serveDynamicAasa(env: Env): Promise<Response> {
  const raw = await env.CONFIG.get('aasa-config', { cacheTtl: 300 });

  if (!raw) {
    return new Response('AASA config not found', { status: 503 });
  }

  let config: AasaConfig;
  try {
    config = JSON.parse(raw) as AasaConfig;
  } catch {
    return new Response('AASA config invalid', { status: 500 });
  }

  const aasa: Record<string, unknown> = {
    applinks: {
      details: [{ appIDs: config.appIDs, components: config.components }],
    },
  };

  if (config.webcredentials?.length) {
    aasa.webcredentials = { apps: config.webcredentials };
  }

  return new Response(JSON.stringify(aasa), {
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'public, max-age=300, s-maxage=3600',
    },
  });
}

// Updating config without a deploy:
// wrangler kv key put --binding CONFIG aasa-config '{"appIDs":["TEAM.com.example.app"],...}'
```

## Cloudflare Cache Rules

Pin the AASA response in Cloudflare's cache so Apple's CDN burst never hits the Worker origin:

```toml
# wrangler.toml
name = "universal-links-worker"
main = "src/index.ts"
compatibility_date = "2025-08-01"

[[kv_namespaces]]
binding = "CONFIG"
id = "<your-kv-id>"

# Cache rule via wrangler Pages or via dashboard:
# Match: /.well-known/apple-app-site-association
# Edge TTL: 3600 s, Browser TTL: 3600 s
```

Alternatively, use a Cloudflare Cache Rule in the dashboard:
- Field: URI Path → equals `/.well-known/apple-app-site-association`
- Action: Cache → Edge TTL: 1 hour, Bypass Cookie: none

## AASA Validation Workflow

```bash
# 1. Verify the file is reachable and returns correct Content-Type
curl -sI https://example.com/.well-known/apple-app-site-association | grep -E 'content-type|cache-control|HTTP'

# 2. Apple's official validator (requires Xcode 15+)
xcrun devicectl device info --device <UDID> --json-output /tmp/device.json

# 3. Use Apple's online AASA validator
open "https://branch.io/resources/aasa-validator/?domain=example.com"

# 4. Validate JSON structure locally
curl -s https://example.com/.well-known/apple-app-site-association | python3 -m json.tool

# 5. Test on device: install app, open Safari, type a matching URL
#    Observe "Open in <App>" banner at top of page
```

## Swift: Handling Incoming Universal Links

```swift
// AppDelegate.swift (UIKit) or App.swift (SwiftUI)
import UIKit

// UIKit
func application(
  _ application: UIApplication,
  continue userActivity: NSUserActivity,
  restorationHandler: @escaping ([UIUserActivityRestoring]?) -> Void
) -> Bool {
  guard userActivity.activityType == NSUserActivityTypeBrowsingWeb,
        let url = userActivity.webpageURL else { return false }

  return handleUniversalLink(url)
}

func handleUniversalLink(_ url: URL) -> Bool {
  let components = URLComponents(url: url, resolvingAgainstBaseURL: true)
  switch components?.path {
  case _ where components?.path.hasPrefix("/products/") == true:
    let slug = String(components!.path.dropFirst("/products/".count))
    Navigator.push(.productDetail(slug: slug))
    return true
  case "/reset-password":
    let token = components?.queryItems?.first(where: { $0.name == "token" })?.value ?? ""
    Navigator.push(.resetPassword(token: token))
    return true
  default:
    return false
  }
}
```

## Anti-patterns
- Serving AASA with a redirect — Apple will not follow more than one redirect and silently fails
- Setting `Content-Type: text/plain` — iOS rejects AASA files not served as `application/json`
- Caching the file for more than 24 hours without a purge mechanism — stale path rules block new links
- Using a wildcard `/*` component without excludes — routes login/settings links into app, breaking web fallback
- Omitting the `TEAMID.` prefix in `appIDs` — causes silent rejection during app install

## Gotchas
- AASA is fetched by Apple's CDN on behalf of the user — your server logs will show Apple IP addresses, not user IPs
- iOS 15.4+ no longer fetches AASA directly from your server at first launch; Apple's CDN caches it for up to 7 days
- The `components` array replaced the older `paths` key in iOS 13 — use `components` for pattern matching
- If a component has `exclude: true`, the path is opened in Safari even if it matches an earlier rule
- Workers must respond within 25 seconds — AASA responses should be under 1 ms, so this is never the bottleneck

## Verification

```bash
# Check Cloudflare cache hit headers
curl -sv https://example.com/.well-known/apple-app-site-association 2>&1 | grep -E 'cf-cache-status|age:'

# Force cache purge after updating AASA
wrangler pages deployment purge --url https://example.com/.well-known/apple-app-site-association

# Simulate Apple's CDN agent
curl -A "AppleCoreMedia/1.0 (iPhone; iOS 17.0)" \
  https://example.com/.well-known/apple-app-site-association

# On physical device: trigger re-validation
# Settings > General > Transfer or Reset iPhone > Reset > Reset Network Settings
# (nuclear — only for testing)
```

## Related
- `deep-linking-universal-app-links.md` — cross-platform deep link strategy
- `ios-universal-links.md` — general Universal Links patterns
- `android-app-links-dynamic-rules-verification.md` — Android equivalent with Digital Asset Links
- `ios-app-clips.md` — App Clips also require AASA entries
- `cloudflare-workers-deep-link-redirect.md` — redirect logic for shared deep-link domains

## Sources
- https://developer.apple.com/documentation/xcode/supporting-universal-links-in-your-app
- https://developer.apple.com/documentation/bundleresources/apple-app-site-association
- https://developers.cloudflare.com/cache/how-to/cache-rules/
- https://developers.cloudflare.com/workers/runtime-apis/response/
- https://branch.io/resources/aasa-validator/
