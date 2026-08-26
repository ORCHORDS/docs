# Cloudflare WAF OWASP ModSecurity Core Ruleset Tuning for Workers APIs

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You enable the Cloudflare Managed Ruleset (OWASP Core Ruleset, CRS) on your zone and immediately see legitimate API traffic blocked or challenged. JSON bodies trigger SQL injection rules because the WAF matches against raw body text. Paths with base64 or numeric IDs trip path-traversal rules. Workers that accept structured API traffic require a different WAF tuning profile than traditional HTML-form web applications.

False positives erode trust in the WAF and push teams to set the managed ruleset to "Log" mode permanently, eliminating its protection. The fix is systematic exception engineering, not disabling the ruleset.

## Context

Cloudflare's WAF managed rulesets implement the OWASP ModSecurity Core Ruleset (CRS) logic adapted for the Cloudflare edge. Rules are grouped by category (SQLi, XSS, LFI, RFI, RCE, etc.) and scored — a request accumulates an anomaly score and is blocked or challenged when it exceeds a configured threshold (default 25 for CRS paranoia level 1).

Workers APIs differ from browser-facing HTML apps in three key ways that affect WAF tuning: (1) bodies are JSON, not URL-encoded form data; (2) clients are often server-side callers without browser User-Agents; (3) legitimate values may contain SQL keywords or shell metacharacters as data (e.g., a code snippet field). Tuning must be done per-API-route rather than globally to maintain coverage on the routes that need it.

## Understanding WAF Anomaly Scoring in Cloudflare

Before writing exceptions, map which rules fire using Firewall Analytics or Security Events in the dashboard.

```bash
# Use the Cloudflare API to pull WAF events and see rule IDs being matched
# Replace ZONE_ID and API_TOKEN with your values

curl -s "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/security/events?since=$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)&action=block&limit=20" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -H "Content-Type: application/json" | \
  jq '.result[] | {rule_id: .rule_id, source: .source, uri: .uri, matched_data: .metadata.matched_data}'
```

Enable Security Events streaming to a Worker via Logpush so you can build a D1 table of false-positive candidates:

```sql
-- D1 schema for WAF false-positive tracking
CREATE TABLE IF NOT EXISTS waf_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  rule_id TEXT NOT NULL,
  action TEXT NOT NULL,
  uri TEXT NOT NULL,
  method TEXT NOT NULL,
  matched_data TEXT,
  user_agent TEXT,
  ip TEXT,
  ts INTEGER NOT NULL,
  confirmed_fp INTEGER DEFAULT 0  -- 1 = confirmed false positive
);

CREATE INDEX idx_waf_rule ON waf_events(rule_id, confirmed_fp);
CREATE INDEX idx_waf_uri ON waf_events(uri, ts);
```

## Writing Precise WAF Rule Exceptions

Cloudflare WAF exceptions are configured in the dashboard under Security → WAF → Managed Rules → Add exception, or via Terraform. Always scope exceptions to the minimum surface: specific HTTP method, URI path prefix, and the rule ID only (not the entire ruleset).

```hcl
# terraform/waf-exceptions.tf

resource "cloudflare_ruleset" "waf_exceptions" {
  zone_id     = var.zone_id
  name        = "WAF exceptions for Workers API"
  description = "Bypass specific CRS rules for JSON API routes"
  kind        = "zone"
  phase       = "http_request_firewall_managed"

  # Exception: Skip SQLi rules for /api/v1/query endpoint that accepts SQL-like DSL
  rules {
    action = "skip"
    action_parameters {
      rules = {
        "efb7b8c949ac4650a09736fc376e9aee" = [  # Cloudflare OWASP managed ruleset ID
          "949110",  # CRS 949110 - Anomaly score threshold exceeded
          "942100",  # CRS 942100 - SQL Injection detected via libinjection
          "942200",  # CRS 942200 - MySQL comment/space-obfuscated injection
        ]
      }
    }
    expression  = "(http.request.method eq \"POST\") and (http.request.uri.path eq \"/api/v1/query\") and (http.request.headers[\"content-type\"] contains \"application/json\")"
    description = "Allow DSL queries to /api/v1/query - validated by Workers input schema"
    enabled     = true
    logging {
      enabled = true  # Keep logging even for skipped rules
    }
  }

  # Exception: Skip path traversal rules for base64-encoded file IDs
  rules {
    action = "skip"
    action_parameters {
      rules = {
        "efb7b8c949ac4650a09736fc376e9aee" = [
          "930100",  # CRS 930100 - Path Traversal Attack (/../)
          "930110",  # CRS 930110 - Path Traversal Attack (/.//)
        ]
      }
    }
    expression  = "(http.request.uri.path matches \"^/api/v1/files/[A-Za-z0-9_-]{20,}$\")"
    description = "File IDs are base64url and trigger path-traversal false positives"
    enabled     = true
  }
}
```

## Custom WAF Rules for Workers-Specific Threats

Beyond tuning managed rules, add custom rules that target attack patterns specific to Workers APIs — things ModSecurity CRS does not cover because they are edge-runtime behaviors.

```hcl
# terraform/custom-waf-rules.tf

resource "cloudflare_ruleset" "workers_custom_waf" {
  zone_id     = var.zone_id
  name        = "Workers API custom WAF rules"
  description = "Attack patterns specific to Workers/D1/R2 APIs"
  kind        = "zone"
  phase       = "http_request_firewall_custom"

  # Block requests with malformed JSON Content-Type but non-JSON body
  rules {
    action      = "block"
    expression  = "(http.request.headers[\"content-type\"] contains \"application/json\") and (not http.request.body.raw matches \"^[\\\\s]*[\\\\[\\\\{]\")"
    description = "Reject claims of JSON body that don't start with { or ["
    enabled     = true
  }

  # Block abnormally large Authorization headers (token stuffing probe)
  rules {
    action      = "block"
    expression  = "len(http.request.headers[\"authorization\"]) > 8192"
    description = "Authorization header > 8KB indicates token stuffing or scanner"
    enabled     = true
  }

  # Challenge requests that set the X-HTTP-Method-Override header (method confusion)
  rules {
    action      = "managed_challenge"
    expression  = "any(http.request.headers.names[*] in {\"x-http-method-override\" \"x-method-override\" \"x-tunneled-method\"})"
    description = "Method override headers are not used by this API; likely scanner"
    enabled     = true
  }

  # Block Workers Binding abuse: direct hits to internal service binding paths
  rules {
    action      = "block"
    expression  = "http.request.uri.path matches \"^/__[a-z]+/\""
    description = "Block probes for internal Cloudflare Workers runtime paths"
    enabled     = true
  }
}
```

## Validating Exceptions with Shadow Mode

Before promoting exceptions to production, test them in log-only mode by setting the WAF to action `"log"` and comparing blocked-vs-logged rates across a 24-hour window.

```typescript
// src/waf-shadow-test.ts
// Worker that compares WAF decisions against your own input validator
// Deploy with a shadow rule that routes a % of traffic here

interface Env {
  DB: D1Database;
  WAF_SHADOW_SAMPLE_RATE: string; // e.g. "0.05" for 5%
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const sampleRate = parseFloat(env.WAF_SHADOW_SAMPLE_RATE ?? "0.05");
    if (Math.random() > sampleRate) {
      return fetch(request); // pass through unsampled requests
    }

    const cfData = request.cf as Record<string, unknown> | undefined;
    const wafScore = cfData?.["threatScore"] as number | undefined;
    const body = await request.clone().text();

    // Run your own schema validation
    let schemaValid = false;
    try {
      const parsed = JSON.parse(body);
      schemaValid = validateApiSchema(parsed, request.url);
    } catch {
      schemaValid = false;
    }

    // Log disagreements: WAF blocks schema-valid traffic = false positive
    if (wafScore !== undefined && wafScore > 25 && schemaValid) {
      await env.DB.prepare(
        `INSERT INTO waf_shadow_log (uri, method, waf_score, schema_valid, ts)
         VALUES (?, ?, ?, ?, unixepoch())`
      ).bind(new URL(request.url).pathname, request.method, wafScore, 1).run();
    }

    return fetch(request);
  },
};

function validateApiSchema(body: unknown, url: string): boolean {
  // Plug in your Zod or JSON Schema validator here
  return typeof body === "object" && body !== null;
}
```

## Anti-patterns

- Setting the OWASP managed ruleset to "Log only" zone-wide — this gives no protection while creating a false sense of coverage
- Writing exceptions that match on `http.request.uri.path contains "/api/"` — too broad; scope to exact paths and methods
- Skipping entire rule categories (e.g., all SQLi rules) rather than specific rule IDs
- Not enabling logging on exception rules — you lose visibility into what would have been blocked
- Tuning based on a single day of traffic — wait for full weekly patterns including batch jobs and CI pipelines
- Treating the WAF as the only SQLi/XSS defense — Workers must still validate and parameterize inputs

## Gotchas

- Cloudflare's managed ruleset IDs change when Cloudflare updates the ruleset version — pin exceptions to rule IDs, not ruleset version hashes, and review after managed ruleset updates
- The `http.request.body.raw` field is only available in WAF custom rules if the request body is under 128KB; larger bodies are not inspected
- CRS paranoia level 2 and above fire on many legitimate API payloads (e.g., long numeric strings trigger integer overflow rules at PL3) — audit before raising paranoia level
- Exception rules are evaluated in order; a broad early exception may shadow a narrower later one — place the most specific exceptions first
- WAF exceptions created in the dashboard are not automatically reflected in Terraform state — import them with `terraform import` before managing with IaC

## Verification

```bash
# 1. Send a known SQLi payload to a protected endpoint and confirm it's blocked
curl -s -o /dev/null -w "%{http_code}" \
  -X POST https://api.example.com/api/v1/protected \
  -H "Content-Type: application/json" \
  -d '{"q": "1 UNION SELECT * FROM users--"}'
# Expect: 403

# 2. Send the same payload to the excepted endpoint and confirm it passes
curl -s -o /dev/null -w "%{http_code}" \
  -X POST https://api.example.com/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"q": "1 UNION SELECT * FROM users--"}'
# Expect: 200 (Worker validates further)

# 3. Check Security Events dashboard to confirm exception was logged (not silently dropped)
# 4. Verify D1 waf_events table is populating via Logpush
```

## Related

- `waf-custom-rules-xss-prevention.md` — XSS-specific custom WAF rule patterns
- `sql-injection-prevention-d1-workers.md` — Worker-side parameterized query enforcement
- `api-schema-validation-openapi-zod-workers.md` — input validation as defense-in-depth behind the WAF
- `rate-limiting-ddos-defense-layers.md` — layering rate limits with WAF rules

## Sources

- OWASP ModSecurity Core Ruleset documentation — https://coreruleset.org/docs/
- Cloudflare WAF Managed Rules documentation — https://developers.cloudflare.com/waf/managed-rules/
- Cloudflare Ruleset Engine expression syntax — https://developers.cloudflare.com/ruleset-engine/rules-language/
