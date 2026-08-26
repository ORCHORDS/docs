# Cloudflare WAF Custom Rules XSS Prevention

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your application accepts user-supplied content—search queries, form fields, URL parameters—and you need to block cross-site scripting (XSS) payloads at the Cloudflare edge before they ever reach your Workers or origin. Managed ruleset detections are firing false positives on your API traffic, or you need tighter, field-specific rules that the default OWASP managed rulesets cannot express.

---

## Context

Cloudflare WAF custom rules run in the `http_request_firewall_custom` phase and evaluate before managed rulesets. They use the Ruleset Engine expression language and can match on any request field—URI, headers, body fields, cookies—using operators such as `contains`, `matches` (PCRE), `lt`, `gt`, and transformation functions like `url_decode`, `html_entity_decode`, `lowercase`, and `remove_bytes`. Custom rules complement, but do not replace, the Cloudflare-managed OWASP core ruleset; layering both gives defence-in-depth.

WAF custom rules are configured via the Cloudflare API or Terraform. For Workers-specific hardening, you can also enforce a second validation layer inside the Worker itself using `HTMLRewriter` or a sanitiser library.

---

## Reflected XSS in URL Parameters

The most common XSS vector for Workers-served applications is reflected input echoed into HTML responses.

Create a WAF custom rule that blocks payloads in query strings:

```typescript
// Cloudflare Ruleset Engine expression (set via API / Terraform, not Workers code)
// Rule: Block XSS patterns in URI query string
// Expression:
// (http.request.uri.query contains "<script" and not http.request.uri.query contains "cdn.example.com")
// or
// (http.request.uri.query matches "(?i)(<script|javascript:|on\\w+=|<iframe|<object|<embed|<svg\\s)")

// Action: block
// Description: XSS patterns in query string
```

Apply via the Cloudflare Rulesets API:

```typescript
// workers/deploy/create-waf-rule.ts
const ZONE_ID = env.CLOUDFLARE_ZONE_ID;
const API_TOKEN = env.CLOUDFLARE_API_TOKEN;

async function createXSSRule(rulesetId: string): Promise<void> {
  const rule = {
    action: "block",
    expression: `(http.request.uri.query matches "(?i)(<script|javascript:|on\\w+=|<iframe|<object|<embed)")`,
    description: "Block XSS patterns in URL query parameters",
    enabled: true,
  };

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets/${rulesetId}/rules`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(rule),
    }
  );

  if (!resp.ok) {
    const err = await resp.json();
    throw new Error(`WAF rule creation failed: ${JSON.stringify(err)}`);
  }
}
```

---

## Stored XSS via Request Body

Body inspection requires the WAF to buffer the request. Enable the Cloudflare body scanning feature and add rules matching POST/PUT bodies:

```typescript
// Expression targeting JSON body fields (Cloudflare WAF body transform functions)
// (http.request.body.raw matches "(?i)(<script|javascript:|on\\w+=)")
// and (http.request.method in {"POST" "PUT" "PATCH"})

// Workers-side secondary validation for defence in depth:
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (["POST", "PUT", "PATCH"].includes(request.method)) {
      const contentType = request.headers.get("content-type") ?? "";

      if (contentType.includes("application/json")) {
        const body = await request.clone().text();
        if (containsXSSPattern(body)) {
          return new Response("Invalid input", { status: 400 });
        }
      }
    }
    return fetch(request);
  },
};

const XSS_PATTERN =
  /<script|javascript:|on\w+\s*=|<iframe|<object|<embed|<svg\s/i;

function containsXSSPattern(input: string): boolean {
  // Decode common encodings before checking
  const decoded = decodeURIComponent(input.replace(/\+/g, " "));
  return XSS_PATTERN.test(decoded) || XSS_PATTERN.test(input);
}
```

---

## DOM XSS via Response Rewriting

When your Worker assembles HTML from untrusted sources (D1 queries, KV values, third-party APIs), use `HTMLRewriter` to strip dangerous attributes before streaming the response:

```typescript
class XSSSanitizer implements HTMLRewriterElementContentHandlers {
  // Remove event handler attributes from all elements
  element(element: Element): void {
    const dangerous = [
      "onclick", "onmouseover", "onerror", "onload", "onfocus",
      "onblur", "onkeyup", "onkeydown", "onsubmit", "onchange",
      "href", "src", "action",
    ];

    for (const attr of dangerous) {
      const val = element.getAttribute(attr);
      if (val && /javascript:|data:/i.test(val)) {
        element.removeAttribute(attr);
      }
    }

    // Remove script tags entirely
    if (element.tagName === "script") {
      element.remove();
    }
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const upstream = await fetch(request);
    const contentType = upstream.headers.get("content-type") ?? "";

    if (!contentType.includes("text/html")) {
      return upstream;
    }

    return new HTMLRewriter()
      .on("*", new XSSSanitizer())
      .transform(upstream);
  },
};
```

---

## WAF Challenge Mode for Suspicious Agents

Rather than hard-blocking all WAF matches (which can harm legitimate users), use the `managed_challenge` action for lower-confidence XSS signals:

```typescript
// Ruleset Engine expression for challenge (not hard block):
// (http.user_agent matches "(?i)(sqlmap|nmap|nikto|dirbuster|masscan)")
// or
// (http.request.uri.query matches "(?i)(<script)" and cf.threat_score lt 50)

// High-confidence patterns → block
// Medium-confidence patterns → managed_challenge
// Logging-only patterns → log action (for tuning)

async function upsertWAFRules(env: Env): Promise<void> {
  const rules = [
    {
      action: "block",
      expression: `(http.request.uri.query matches "(?i)(<script\\b|javascript:\\s*[a-z])")`,
      description: "High-confidence XSS – block",
      enabled: true,
    },
    {
      action: "managed_challenge",
      expression: `(http.request.uri.query matches "(?i)(on\\w+\\s*=)")`,
      description: "Medium-confidence XSS – challenge",
      enabled: true,
    },
    {
      action: "log",
      expression: `(http.request.uri.query matches "(?i)(<[a-z]+ )")`,
      description: "HTML tags in QS – log only for tuning",
      enabled: true,
    },
  ];

  // POST each rule to your zone's custom ruleset via the Cloudflare API
  for (const rule of rules) {
    await postRule(rule, env);
  }
}

async function postRule(rule: object, env: Env): Promise<void> {
  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${env.ZONE_ID}/rulesets/${env.RULESET_ID}/rules`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(rule),
    }
  );
  if (!resp.ok) throw new Error(`Rule POST failed: ${resp.status}`);
}
```

---

## Content-Security-Policy as Last Line of Defence

Even with WAF rules, always emit a restrictive CSP from your Worker to contain any XSS that slips through:

```typescript
function addSecurityHeaders(response: Response): Response {
  const headers = new Headers(response.headers);

  // Nonce-based CSP prevents inline script execution
  const nonce = crypto.randomUUID().replace(/-/g, "");
  headers.set(
    "Content-Security-Policy",
    [
      `script-src 'nonce-${nonce}' 'strict-dynamic'`,
      "object-src 'none'",
      "base-uri 'self'",
      "require-trusted-types-for 'script'",
    ].join("; ")
  );

  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("X-Frame-Options", "DENY");

  return new Response(response.body, { status: response.status, headers });
}
```

---

## Anti-patterns

- **Relying solely on managed rulesets**: OWASP managed rules have tunable paranoia levels but cannot express field-specific logic—combine them with custom rules for your app's unique surfaces.
- **Blocking on `matches` without `url_decode` transform**: Attackers encode payloads as `%3Cscript%3E`; always chain transformations (`http.request.uri.query` is URL-decoded by default in Cloudflare expressions, but body inspection may not be).
- **Using `contains` with short strings like `<sc`**: Too broad; causes false positives on encoded HTML in legitimate JSON APIs.
- **Setting all rules to `block` immediately**: Start with `log` action, review Security Events dashboard for a week, then promote to `managed_challenge` then `block`.
- **Forgetting the `OPTIONS` method**: WAF body rules that match POST often inadvertently flag preflight requests; add `and http.request.method ne "OPTIONS"` to body-inspection expressions.

---

## Gotchas

- **Body inspection is limited**: Cloudflare WAF body scanning has a default 128 KB limit; payloads beyond this are not inspected. Enforce size limits in your Worker.
- **Expression length limits**: Cloudflare custom rule expressions are limited to 4 096 characters; split complex XSS logic across multiple rules.
- **Regex dialect**: Cloudflare WAF uses RE2 syntax (no lookaheads/lookbehinds); adapt PCRE-heavy patterns accordingly.
- **Bypass via encoding**: Attackers chain URL, HTML entity, and Unicode encodings. Test your rules with `<script>`, `%3Cscript%3E`, `&#x3C;script`, and `<script` variants.
- **API token scope**: The token used to create WAF rules needs the `Zone.Firewall Services:Edit` permission, not the generic `Zone:Edit`.

---

## Verification

```bash
# 1. Test your WAF rule with a benign XSS probe (use your own zone)
curl -si "https://your-worker.example.com/search?q=<script>alert(1)</script>" \
  | grep -E "^HTTP|cf-ray|x-blocked-by"

# 2. Check Security Events in the Cloudflare dashboard:
#    Security → Events → filter by Rule ID

# 3. Verify CSP header is present
curl -si "https://your-worker.example.com/" \
  | grep -i "content-security-policy"

# 4. Run OWASP ZAP or Burp Suite active scan against your staging zone
# 5. Review WAF Analytics for false-positive rate over 48 h before enabling block mode
```

---

## Related

- `xss-htmlrewriter-sanitization-workers.md`
- `content-security-policy-workers-nonce.md`
- `workers-ddos-layer7-custom-firewall-rules.md`
- `waf-rules-configuration.md`
- `cloudflare-waf-mobile-api-false-positives.md`

---

## Sources

- Cloudflare WAF custom rules documentation: https://developers.cloudflare.com/waf/custom-rules/
- Cloudflare Ruleset Engine expression language: https://developers.cloudflare.com/ruleset-engine/rules-language/
- OWASP XSS Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html
- Cloudflare WAF managed rulesets: https://developers.cloudflare.com/waf/managed-rules/
- Cloudflare body scanning: https://developers.cloudflare.com/waf/about/payload-logging/
