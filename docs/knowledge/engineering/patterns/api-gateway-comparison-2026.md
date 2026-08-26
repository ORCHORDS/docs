# api-gateway-comparison-2026

**Issue:** API gateway choice — Kong vs Apigee vs others
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have 50 microservices. 200 endpoints. You need
auth, rate limit, monetization. You don't know which
gateway. Kong? Apigee? Cloudflare? AWS? You wish
you had a comparison.

## Root cause
**No gateway = every team reinvents auth + rate
limit + auth.** Pick a gateway.

**Source:** Zuplo 2026 + API7 2026.

## The "gateway" concept

API gateway:
- **Routing:** /users → user-service
- **Auth:** API key, OAuth, JWT
- **Rate limit:** Per key, per route
- **Transform:** Request/response
- **Observability:** Logs, metrics
- **Monetization:** Per tier

The gateway is the front door.

## The "Kong" pattern

For Kong:
- **Built on:** NGINX + OpenResty
- **License:** OSS Apache 2.0
- **Deployment:** Self-hosted (K8s) or Konnect
- **Plugin ecosystem:** 300+ plugins
- **Performance:** High, sub-ms latency
- **Lang:** Lua + Go plugins
- **Pricing:** Free OSS / Konnect Plus $105/mo /
  Enterprise $40K-250K/yr

The Kong is K8s-native.

## The "Apigee" pattern

For Apigee:
- **Built on:** Google Cloud
- **License:** Commercial
- **Deployment:** Fully managed on GCP / hybrid
- **Strengths:** Analytics, monetization, governance
- **Performance:** Lower (legacy architecture)
- **Lang:** XML policies, JavaScript, Java
- **Pricing:** $20/M + $365/env/mo to $2,500+/mo

The Apigee is GCP-tied.

## The "AWS API Gateway" pattern

For AWS:
- **Built on:** AWS Lambda integration
- **License:** Commercial
- **Deployment:** Fully managed
- **Strengths:** Tight Lambda, IAM, usage plans
- **Limitations:** Not full mgmt platform
- **Pricing:** Per request

The AWS is serverless.

## The "Cloudflare API Shield" pattern

For Cloudflare:
- **Built on:** Edge network
- **License:** Commercial
- **Deployment:** Global edge
- **Strengths:** mTLS, schema validation, bot mgmt
- **Limitations:** No developer portal, no mgmt UI
- **Pricing:** Per request

The Cloudflare is edge.

## The "Kong vs Apigee" pattern

For choice:
| Dim | Kong | Apigee |
|---|---|---|
| QPS | High (NGINX) | Lower (legacy) |
| Latency | Sub-ms | Moderate |
| Plugins | 300+ | Limited |
| Hot reload | Constrained | Constrained |
| License | OSS Apache | Commercial |
| Cloud | Multi | GCP-tied |
| Lock-in | Moderate | High |
| Cost | Free-$250K | $25K-100K |

The choice is per need.

## The "Apache APISIX" pattern

For APISIX:
- **License:** Apache 2.0
- **QPS:** 23K single-core (2x Kong)
- **Latency:** 0.2ms avg
- **Plugins:** 100+ OSS
- **Lang:** Go, Java, Python, Wasm, Lua
- **Lock-in:** None (Apache Foundation)

The APISIX is fast + OSS.

## The "Zuplo" pattern

For Zuplo:
- **Type:** Edge-native, fully managed
- **Deploy:** 300+ data centers in 20s
- **Lang:** TypeScript (not XML or Lua)
- **AI/MCP:** Built-in
- **Monetization:** Stripe
- **Compliance:** SOC 2 Type II

The Zuplo is developer-first.

## The "Azure API Management" pattern

For Azure APIM:
- **Built on:** Azure
- **Strengths:** Azure AD, deep Azure
- **Limitations:** XML policies, slow provisioning
- **Pricing:** Per tier

The Azure is for Microsoft.

## The "Tyk" pattern

For Tyk:
- **Type:** OSS self-hosted
- **Strengths:** GraphQL, Open source
- **Limitations:** Mgmt UI is paid
- **Pricing:** Free OSS / paid Dashboard

The Tyk is OSS.

## The "MuleSoft" pattern

For MuleSoft:
- **Type:** Enterprise
- **Strengths:** Full lifecycle
- **Limitations:** Expensive
- **Pricing:** $100K+/yr

The MuleSoft is enterprise.

## The "decision matrix" pattern

For choice:
| Situation | Pick |
|---|---|
| K8s-native + multi-cloud + Lua | Kong |
| GCP + monetization + analytics | Apigee |
| AWS Lambda + serverless | AWS API Gateway |
| Edge + security + global | Cloudflare |
| Microsoft + Azure AD | Azure APIM |
| OSS + GraphQL | Tyk |
| Apache + max QPS | APISIX |
| Developer-first + TypeScript + edge | Zuplo |
| Enterprise + lifecycle | MuleSoft |

The choice is per situation.

## The "Cloudflare API Shield" features

For Cloudflare:
- **mTLS:** Client cert auth
- **Schema validation:** Stop bad requests
- **API Shield:** Bot + abuse
- **Rate limit:** At edge
- **No:** Developer portal, mgmt UI, monetization

The Cloudflare is partial.

## The "what NOT a gateway" pattern

For routing-only:
- **AWS API Gateway:** Routing + Lambda
- **Cloudflare API Gateway:** Routing + security
- **Not:** Developer portal, key mgmt, monetization

The routing is only one piece.

## The "full mgmt platform" pattern

For full:
- **Zuplo:** TypeScript + edge + monetization
- **Kong Konnect:** Plugin ecosystem + paid
- **Apigee:** Analytics + governance
- **Azure APIM:** Azure AD + policies
- **MuleSoft:** Full lifecycle

The full is broader.

## The "lock-in" pattern

For lock-in:
- **Apigee:** High (GCP)
- **Kong:** Moderate (paid features)
- **AWS API GW:** High (AWS)
- **Cloudflare:** Moderate
- **APISIX / Tyk:** None (OSS)
- **Zuplo:** Low (TypeScript, GitOps)

The lock-in is per vendor.

## The "performance" pattern

For perf:
- **APISIX:** 23K QPS, 0.2ms
- **Kong:** High (NGINX)
- **Apigee:** Lower
- **Cloudflare:** Edge-fast
- **AWS API GW:** Variable

The perf is per use.

## The "AI / MCP" pattern

For AI workloads:
- **MCP:** Model Context Protocol
- **Built-in:** Zuplo, Cloudflare AI Gateway
- **Add via plugin:** Kong, APISIX
- **None:** Apigee (legacy)

The AI is emerging.

## The "self-host vs SaaS" pattern

For deployment:
- **Self-host:** Kong, Tyk, APISIX, MuleSoft
- **SaaS:** Apigee, Zuplo, Cloudflare
- **Hybrid:** Kong Konnect, Apigee Hybrid

The choice is per team.

## The "no gateway" anti-pattern

For no gateway:
- **Issue:** Each service has auth + rate limit
- **Result:** Inconsistency, security gaps
- **Fix:** Centralized gateway

The gateway is required.

## The "vendor lock-in" anti-pattern

For lock-in:
- **Issue:** Hard to migrate
- **Fix:** Open standards (OpenAPI, OAuth)

The standards are open.

## The "wrong size" anti-pattern

For wrong size:
- **Issue:** Cloud-native org uses Apigee (overkill)
- **Or:** Enterprise uses Cloudflare (underkill)
- **Fix:** Match size to org

The size is matched.

## The "AI workload" anti-pattern

For AI without gateway:
- **Issue:** Token abuse, cost spike
- **Fix:** AI Gateway (Cloudflare, Zuplo)

The AI is gated.

## The "gateway checklist" pattern

For checklist:
- [ ] Auth method supported
- [ ] Rate limit configured
- [ ] Observability integrated
- [ ] Plugin ecosystem
- [ ] Lock-in acceptable
- [ ] Cost model fits
- [ ] Performance meets SLA
- [ ] AI/MCP ready (if needed)
- [ ] GitOps support
- [ ] SOC 2 / compliance

The checklist is 10.

## Verification
- **Test:** Routes work
- **Test:** Auth enforced
- **Test:** Rate limit hits
- **Test:** Observability streams
- **Audit:** Quarterly

## Gotchas
- **The "no gateway" anti-pattern.** Centralize.
- **The "wrong size" anti-pattern.** Match.
- **The "lock-in" anti-pattern.** Open standards.

## Related
- `cloudflare/waf-best-practices.md`
- `cloudflare/waf-rate-limiting-deep-dive.md`
- `patterns/api-design-best-practices.md`
- `security/owasp-api-top-10-2023.md`
- `patterns/webhook-reliability.md`
- Zuplo: https://zuplo.com/learning-center/kong-vs-apigee-api-gateway-comparison-2026
- Zuplo: https://zuplo.com/learning-center/best-api-management-platforms-2026
- API7: https://api7.ai/apigee-vs-kong
