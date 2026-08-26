# Cloudflare WAF False Positives for Mobile API Clients

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

example project API calls from the React Native app are intermittently blocked with HTTP 403 responses
containing a Cloudflare challenge page (HTML body despite `Accept: application/json`). The
errors affect roughly 0.3–1.2% of API requests from mobile clients, but only 0.02% from
desktop browsers. The blocked requests appear in the Cloudflare WAF Firewall Events dashboard
with rule categories `OWASP`, `Managed Rules`, or custom rate-limit rules. Retrying the same
request immediately after a block often succeeds. Users affected are never the same ones
repeatedly — it appears random across the mobile user base.

## Context

Cloudflare's WAF evaluates every request against a rule set that was primarily designed for
browser-originated traffic. Mobile API clients differ from browsers in ways that the WAF
interprets as anomalous or malicious:

1. **User-Agent strings**: React Native's default UA (`okhttp/4.x` on Android,
   `<AppName>/1.0 CFNetwork/1410 Darwin/22.6.0` on iOS) does not match any browser pattern.
   Some WAF rules assign a higher threat score to non-browser UAs, particularly when combined
   with other signals.

2. **Carrier NAT and shared IPs**: Mobile users on cellular networks often share a single
   public IPv4 address with thousands of other users via CGNAT. Cloudflare's rate-limiting and
   reputation scoring is partially IP-based. A malicious user on the same CGNAT pool can taint
   the IP's reputation for all other users sharing it. Cloudflare's `carrier-grade NAT`
   detection attempts to handle this, but false positives persist.

3. **Request headers**: Mobile clients often omit headers that browsers always send (`Accept-Language`,
   `Accept-Encoding`, `Sec-Fetch-*` prefetch headers, `Referer`). Some OWASP WAF rules treat
   missing browser-standard headers as a signal of automated/bot traffic, raising the threat score.

4. **JSON POST bodies with unusual encoding**: React Native's `fetch` serialises JSON with
   standard `JSON.stringify`, but some Expo/RN versions have emitted malformed UTF-8 sequences
   in edge cases (emoji handling, null characters). Cloudflare's WAF Content Inspection rules
   occasionally flag these as injection attempts.

5. **Rapid successive requests from app startup**: At example project app launch, the client fires
   3–5 parallel API requests (session validation, feature flags, feed, notifications). This
   burst pattern can trigger rate-limit rules designed to catch scraping bots.

6. **React Native Hermes sending `Transfer-Encoding: chunked` for POST bodies**: On some RN
   versions, POST requests with a JSON body are sent as chunked transfer even for small
   payloads. Some WAF rules flag chunked POST requests from non-browser UAs as suspicious.

## Section 1 — Diagnosing WAF Blocks in Cloudflare Dashboard

```
Navigation: Security → WAF → Firewall Events
Filters:
  - Action: block / challenge
  - Service: Cloudflare Managed Rules / OWASP / Custom Rules
Key fields to examine:
  - "Rule ID" — identifies the specific rule triggering the block
  - "User Agent" — confirm it's the RN UA pattern
  - "IP" — check if it's a CGNAT range (large ASN like T-Mobile, Verizon)
  - "Ray ID" — correlate with app-side error logs using X-Request-Id header
```

```bash
# Pull WAF events via API for programmatic analysis
curl -s "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/firewall/events" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -G \
  --data-urlencode "per_page=50" \
  --data-urlencode "action=block" \
  | jq '.result[] | {ray_id, rule_id, action, user_agent, ip, timestamp}'
```

## Section 2 — WAF Configuration for Mobile API Traffic

The safest approach for a mobile-first API is to create a WAF Custom Rule that bypasses managed
rules for verified mobile API requests and applies a dedicated, lighter rule set:

```
# Cloudflare WAF Custom Rule — Skip managed rules for authenticated mobile API traffic
# Configure in: Security → WAF → Custom Rules

Rule Name: "Skip managed WAF for authenticated mobile API"
Expression:
  (http.request.uri.path wildcard "/api/*")
  AND
  (http.request.headers["Authorization"][0] matches "^Bearer [A-Za-z0-9._-]{20,}")
  AND
  (
    (http.user_agent contains "okhttp")
    OR (http.user_agent contains "CFNetwork")
    OR (http.user_agent contains "Expo")
    OR (http.user_agent contains "example project")
  )
Action: Skip → Cloudflare Managed Rules (NOT the OWASP ruleset — keep OWASP for injection protection)
```

This rule bypasses the browser-oriented managed rules for authenticated requests from known
mobile UAs, while keeping OWASP injection rules active (important for API security).

**For unauthenticated mobile endpoints (registration, login):**

```
# Custom Rule: Lower threat score threshold for mobile auth endpoints
Rule Name: "Relax score threshold for mobile auth"
Expression:
  (http.request.uri.path in {"/api/auth/register" "/api/auth/login"})
  AND (cf.threat_score lt 50)  # Default is 14; raise for known mobile IPs
Action: Allow
Priority: Above managed rules
```

## Section 3 — Sending Mobile-Friendly Request Headers from React Native

Configuring RN to send headers that reduce WAF anomaly scoring:

```typescript
// src/api/client.ts — WAF-friendly React Native API client
import { Platform, NativeModules } from 'react-native';

const APP_VERSION = '1.2.0';
const BUILD_NUMBER = '42';

// Build a browser-adjacent UA string to reduce WAF friction
// This is not spoofing — it identifies the app + platform accurately
// while including version signals the WAF treats as lower-risk
function buildUserAgent(): string {
  if (Platform.OS === 'android') {
    const { Version } = Platform;
    // Append a "compatible" browser token to reduce non-browser UA penalty
    return `WASPApp/${APP_VERSION} (Android ${Version}; Build/${BUILD_NUMBER}) okhttp/4.12.0`;
  }
  if (Platform.OS === 'ios') {
    const { osVersion } = Platform;
    return `WASPApp/${APP_VERSION} (iOS ${osVersion}; Build/${BUILD_NUMBER})`;
  }
  return `WASPApp/${APP_VERSION}`;
}

const UA = buildUserAgent();

export async function apiRequest<T>(
  path: string,
  options: RequestInit & { token?: string } = {}
): Promise<T> {
  const { token, ...fetchOptions } = options;

  const headers: Record<string, string> = {
    'User-Agent': UA,
    'Accept': 'application/json',
    'Accept-Language': 'en-US,en;q=0.9', // Absence of Accept-Language raises WAF score
    'Accept-Encoding': 'gzip, deflate, br', // Expected by WAF rules
    'Content-Type': 'application/json',
    ...(fetchOptions.headers as Record<string, string> ?? {}),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // Include a custom header to identify mobile API traffic for WAF exemption rules
  headers['X-Client-Type'] = 'mobile-app';
  headers['X-App-Version'] = APP_VERSION;

  const response = await fetch(`https://api.example.com${path}`, {
    ...fetchOptions,
    headers,
  });

  // Detect WAF challenge page (HTML body) for a JSON-expecting request
  const contentType = response.headers.get('content-type') ?? '';
  if (response.status === 403 && contentType.includes('text/html')) {
    // WAF block — extract Cloudflare ray ID for reporting
    const rayId = response.headers.get('cf-ray') ?? 'unknown';
    const err = new Error(`WAF_BLOCK:${rayId}`);
    (err as any).wafBlock = true;
    (err as any).rayId = rayId;
    throw err;
  }

  if (!response.ok) {
    throw new Error(`HTTP_${response.status}`);
  }

  return response.json() as Promise<T>;
}
```

## Section 4 — Staggering App Startup Requests to Avoid Rate-Limit Rules

```typescript
// src/startup/init.ts — stagger parallel startup requests to avoid burst detection
import { apiClient } from '../api/client';

// Naïve: all 5 requests fire simultaneously — triggers rate-limit WAF rules
// Promise.all([fetchSession(), fetchFlags(), fetchFeed(), fetchNotifications(), fetchProfile()])

// Better: stagger with small delays — mimics browser sequential waterfall
export async function initializeApp(token: string): Promise<void> {
  // Critical path first — session must succeed before anything else
  const session = await apiClient.get('/api/auth/session', token);
  if (!session) return; // Not authenticated — skip rest

  // Feature flags are fast (KV-backed), fire immediately after session
  const flagsPromise = apiClient.get('/api/flags', token);

  // Stagger data requests by 100-200 ms to avoid simultaneous burst
  await new Promise(r => setTimeout(r, 100));
  const feedPromise = apiClient.get('/api/feed', token);

  await new Promise(r => setTimeout(r, 100));
  const notificationsPromise = apiClient.get('/api/notifications', token);

  // Wait for all data requests to resolve
  await Promise.all([flagsPromise, feedPromise, notificationsPromise]);
}
```

## Section 5 — Handling WAF Blocks Gracefully in React Native

```typescript
// src/hooks/useApiRequest.ts
import { useCallback } from 'react';
import * as Sentry from '@sentry/react-native';

export function useApiRequest() {
  const request = useCallback(async <T>(
    path: string,
    options?: RequestInit & { token?: string }
  ): Promise<T | null> => {
    try {
      return await apiRequest<T>(path, options);
    } catch (err) {
      if (err instanceof Error && (err as any).wafBlock) {
        // WAF block — report to monitoring with ray ID, show user-friendly message
        const rayId = (err as any).rayId;
        Sentry.captureEvent({
          message: 'WAF block on mobile API request',
          level: 'warning',
          tags: { ray_id: rayId, path },
        });

        // Don't show "403 Forbidden" to the user — that's confusing
        // Show a neutral retry message instead
        showToast('Something went wrong. Please try again in a moment.');
        return null;
      }
      throw err; // Re-throw non-WAF errors
    }
  }, []);

  return { request };
}
```

## Anti-patterns

- **Using the default `okhttp/4.x` or bare `CFNetwork` UA string without app identification**:
  These UAs have no app context and match common scraping tool signatures. Always append the
  app name and version to help WAF analysis and support debugging.
- **Omitting `Accept-Language` and `Accept-Encoding` headers**: These are present in every
  legitimate browser request. Their absence is a WAF signal for automated traffic. Include them
  even for JSON API calls.
- **Sending burst requests at app startup without staggering**: 5 simultaneous requests from
  a CGNAT IP with a non-browser UA is indistinguishable from a simple scraper. Stagger or
  sequence critical startup fetches.
- **Silently swallowing WAF 403 errors as generic network errors**: WAF blocks need visibility
  in monitoring. Log the `cf-ray` ID — it is the key that correlates the WAF event in the
  Cloudflare dashboard with your app-side error.
- **Skipping all WAF rules for mobile clients to avoid false positives**: This removes injection
  protection (SQLi, XSS, path traversal). The correct approach is to skip the *browser-behavioural*
  managed rules while keeping OWASP injection rules active.
- **Setting WAF rule to allow all `/api/*` traffic**: This completely bypasses WAF for the
  highest-risk attack surface. Scope the bypass to authenticated requests with known UA patterns.

## Gotchas

- **Cloudflare's Bot Score (separate from WAF threat score) also affects mobile**: The Bot
  Fight Mode or Super Bot Fight Mode can independently challenge non-browser UAs. Check
  Security → Bots in the dashboard. Super Bot Fight Mode does not allow per-rule exemptions —
  you must disable it entirely for API subdomains or use Bot Management (Enterprise).
- **The `Sec-Fetch-*` header family is browser-only.** Some WAF rules check for the absence
  of `Sec-Fetch-Site` or `Sec-Fetch-Mode` to detect non-browser clients. These are
  automatically added by Chromium browsers but should NOT be sent by React Native — sending
  fake `Sec-Fetch-*` headers is considered header spoofing and may cause other issues.
- **Cloudflare WAF `X-Client-Type` custom header exemption requires a paid plan.** Custom
  rule expressions that filter on custom request headers are not available on the Free plan.
  On Free, the only reliable approach is UA-based exemption.
- **The WAF block response is HTML, not JSON**, even when the request carries `Accept: application/json`.
  Mobile clients must check `Content-Type` of 403 responses to distinguish WAF blocks from
  application-level 403 errors (authentication failure, etc.).
- **Cloudflare Managed Ruleset updates can re-introduce regressions.** Managed rules are
  updated by Cloudflare without warning. A rule that worked fine for months may start blocking
  mobile clients after a ruleset update. Subscribe to Cloudflare's WAF changelog or set up
  an alert on Firewall Events spike in Cloudflare Notifications.

## Verification

```bash
# Test if your mobile UA triggers WAF blocks
curl -s -o /dev/null -w "%{http_code}" \
  -H 'User-Agent: okhttp/4.12.0' \
  -H 'Accept: application/json' \
  -H 'Authorization: Bearer test-token' \
  https://api.example.com/api/feed
# Expect 200 or 401, NOT 403

# Send 10 rapid requests to test burst rate-limit rule
for i in $(seq 1 10); do
  curl -s -o /dev/null -w "%{http_code} " \
    -H 'User-Agent: WASPApp/1.0 (Android 14)' \
    -H 'Authorization: Bearer test-token' \
    https://api.example.com/api/feed &
done
wait
# Any 429 or 403 in the output indicates burst rate-limit trigger

# Verify WAF bypass rule is active by checking if managed rules are skipped
# Look in Cloudflare Dashboard: Security → WAF → Firewall Events → filter for your test Ray ID
```

## Related

- `carrier-cgnat-shared-ip-rate-limiting.md`
- `mobile-network-resilience-cloudflare-workers.md`
- `cloudflare-kv-read-latency-mobile-highlatency-vs-desktop.md`
- `mobile-jwt-storage-pitfalls.md`
- `jailbreak-root-detection.md`

## Sources

- Cloudflare WAF docs: Managed Rules and OWASP Core Ruleset
- Cloudflare Community: "Mobile app getting 403 from WAF" threads
- OWASP CRS (Core Rule Set) documentation: paranoia levels and UA anomaly scoring
- Cloudflare Blog: "Bot Management for Mobile Applications"
- React Native docs: Networking — default headers and User-Agent behaviour
- Android OkHttp source: default headers sent with every request
